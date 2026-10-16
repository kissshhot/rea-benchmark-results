"""Release-only build recipes adapted from the private v5 pipeline.

Business implementations, reference solutions, tests and semantic mutants are
deliberately absent. Inputs are reviewed local source bundles; tools are supplied
by the caller. These portable recipes do not replace the frozen experiment builds.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import zipfile


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def read(root, name):
    path = root / name
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        raise ValueError("Unsafe or missing source: " + name)
    return path.read_text(encoding="utf-8")


def replace(text, old, new):
    if old not in text:
        raise ValueError("Source bundle does not match the reviewed recipe")
    return text.replace(old, new)


class Build:
    def __init__(self, config, source, work, release):
        self.config, self.source, self.work, self.release = config, source, work, release
        self.logs = []
        self.env = dict(os.environ)
        self.env.update(config.get("build_environment", {}))

    def tool(self, name):
        return self.config.get("tools", {}).get(name, name)

    def run(self, argv, cwd=None):
        argv = list(map(str, argv))
        start = time.monotonic()
        result = subprocess.run(argv, cwd=cwd, env=self.env, capture_output=True,
                                text=True, timeout=300, check=False)
        self.logs.append({"argv": argv, "seconds": time.monotonic() - start,
                          "exit_code": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError("Build failed; inspect the local build log: " + argv[0])
        return result.stdout

    def resources(self):
        # Explicit file list; never recursively copy a source/private directory.
        for name in self.config.get("resources", ["LICENSE.txt"]):
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe resource path")
            write(self.release / path, read(self.source, name))


def native(b, mixed):
    host = read(b.source, "host.c")
    common = read(b.source, "common.h")
    if mixed:
        host = replace(host, '"run_job"', '"r7"')
        common = replace(common, "#define ENTRY run_job", "#define ENTRY r7")
        common = replace(common, "return process(in,aux,out,o);",
                         "jobfn volatile route=process; return route(in,aux,out,o);")
        common += '\n__attribute__((visibility("default"))) unsigned legacy_checksum(unsigned x){return x*17u+31u;}\n'
    for name, text in [("host.c", host), ("common.h", common),
                       ("kernel.c", read(b.source, "kernel.c"))]:
        write(b.work / name, text)
    host_name = "runtime/q7" if mixed else "app"
    library = "components/m4.dylib" if mixed else "libmodule.dylib"
    for name in [host_name, library]:
        (b.release / name).parent.mkdir(parents=True, exist_ok=True)
    flags = ["-mmacosx-version-min=13.0", "-fvisibility=hidden", "-O2"]
    b.run([b.tool("clang"), *flags, b.work / "host.c", "-o", b.release / host_name])
    b.run([b.tool("clang"), *flags, "-dynamiclib", b.work / "kernel.c", "-o", b.release / library])
    b.run([b.tool("strip"), "-x", b.release / host_name, b.release / library])
    catalog = None
    if (b.source / "catalog.tsv").exists():
        catalog = "resources/p4.dat" if mixed else "catalog.tsv"
        write(b.release / catalog, read(b.source, "catalog.tsv"))
    if mixed:
        write(b.release / "resources/retired-profile.dat", "legacy-profile=17\nrender-mode=archived\n")
    write(b.release / "manifest.json", json.dumps({"host": host_name, "library": library,
          "entry_symbol": "r7" if mixed else "run_job", "catalog": catalog}))


GATEWAY = '''using System.Text.Json;using Core;
object Invoke(JsonElement q){if(q.TryGetProperty("op",out var op)&&op.GetString()=="health")return new{health=73};return Engine.Execute(q);}
string Process(string line){using var d=JsonDocument.Parse(line);return JsonSerializer.Serialize(Invoke(d.RootElement));}
if(args.Length==3&&args[0]=="--request"){File.WriteAllText(args[2],Process(File.ReadAllText(args[1]))+"\\n");}else{string? line;while((line=Console.ReadLine())!=null)Console.WriteLine(Process(line));}
'''


def dotnet(b, mixed):
    texts = {name: read(b.source, name) for name in ["Engine.cs", "Rules.cs"]}
    policy, gateway = read(b.source, "policy.json"), GATEWAY
    if mixed:
        for name, text in texts.items():
            for old, new in [("namespace Core;", "namespace RuntimeN;"),
                             ("using Policy;", "using RuntimeP;"),
                             ("namespace Policy;", "namespace RuntimeP;"),
                             ("Engine", "M7"), ("Rules", "P3"),
                             ('"policy.json"', '"assets/r12.json"')]:
                text = text.replace(old, new)
            texts[name] = text
        texts["Engine.cs"] += '\npublic static class Compatibility { public static int GuessCapacity(int x)=>x*17+31;}\n'
        gateway = gateway.replace("using Core;", "using System.Reflection;")
        gateway = replace(gateway, "return Engine.Execute(q);", 'using var routes=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"routes.json")));var r=routes.RootElement;var type=Assembly.Load(r.GetProperty("assembly").GetString()!).GetType(r.GetProperty("type").GetString()!)!;return type.GetMethod(r.GetProperty("method").GetString()!)!.Invoke(null,new object[]{q})!;')
        write(b.release / "assets/r12.json", policy)
        write(b.release / "routes.json", json.dumps({"assembly": "ModuleA", "type": "RuntimeN.M7", "method": "Execute"}))
        write(b.release / "compatibility.json", '{"profile":"legacy","enabled":false,"capacity":999}')
    else:
        write(b.release / "policy.json", policy)
    write(b.work / "Directory.Build.props", '<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><DebugType>none</DebugType><DebugSymbols>false</DebugSymbols><Deterministic>true</Deterministic></PropertyGroup></Project>')
    write(b.work / "Gateway/Gateway.csproj", '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType></PropertyGroup><ItemGroup><ProjectReference Include="../Core/Core.csproj"/></ItemGroup></Project>')
    for project, assembly, reference in [("Core", "ModuleA" if mixed else "Core", '<ItemGroup><ProjectReference Include="../Policy/Policy.csproj"/></ItemGroup>'), ("Policy", "ModuleB" if mixed else "Policy", "")]:
        write(b.work / project / (project + ".csproj"), '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><AssemblyName>' + assembly + '</AssemblyName></PropertyGroup>' + reference + '</Project>')
    write(b.work / "Gateway/Program.cs", gateway)
    write(b.work / "Core/Engine.cs", texts["Engine.cs"])
    write(b.work / "Policy/Rules.cs", texts["Rules.cs"])
    b.run([b.tool("dotnet"), "publish", b.work / "Gateway/Gateway.csproj", "-c", "Release", "-o", b.release, "--ignore-failed-sources"])


def wasm(b, mixed):
    code = read(b.source, "kernel.ts")
    if not mixed:
        code = re.sub(r"export function (legacy_decode|obsolete_blend|old_offset|legacy_packing)\([^\n]+\n", "", code)
    write(b.work / "kernel.ts", code)
    b.run([b.tool("node"), b.tool("asc"), b.work / "kernel.ts", "--outFile", b.work / "raw.wasm", "--runtime", "stub", "--memoryBase", "131072", "--initialMemory", "16", "--optimize", "--noAssert"])
    wat = b.run([b.tool("wasm2wat"), b.work / "raw.wasm"])
    module, entry, health = "kernel.wasm", "run", "health"
    if mixed:
        wat = replace(wat, '(export "run"', '(export "x7"')
        wat = replace(wat, '(export "health"', '(export "x2"')
        module, entry, health = "chunks/a91.wasm", "x7", "x2"
        write(b.release / "routing.mjs", "export function invoke(exports,key){const dispatch=new Map([[key,()=>exports[key]()]]);return dispatch.get(key)();}\n")
        write(b.release / "legacy-profiles.json", '{"profile":"compatibility-v1","enabled":false,"bias":17}')
    write(b.work / "kernel.wat", wat)
    (b.release / module).parent.mkdir(parents=True, exist_ok=True)
    b.run([b.tool("wat2wasm"), b.work / "kernel.wat", "-o", b.release / module])
    b.run([b.tool("wasm-validate"), b.release / module])
    write(b.release / "host.mjs", read(b.source, "host.mjs"))
    write(b.release / "manifest.json", json.dumps({"kind": b.config["kind"], "module": module, "entry": entry, "health": health, "routing": "./routing.mjs" if mixed else None}))


def plugin(b, mixed):
    core = read(b.source, "engine.js")
    files = {"entry.js": read(b.source, "entry.js")}
    if mixed:
        files["p07.js"] = replace(core, "exports.execute", "exports.q7")
        files["engine.js"] = "const r=require('./p07');const dispatch=new Map([['active',r.q7],['legacy',()=>({unavailable:true})]]);exports.execute=(...args)=>dispatch.get('active')(...args);\n"
        files["compatibility.js"] = "exports.convertLegacy=x=>String(x).split(';').reverse().join(',');exports.version=0;\n"
    else:
        files["engine.js"] = core
    package = b.work / "extension"
    manifest = json.loads(read(b.source, "package.json"))
    manifest["main"] = "./dist/entry.js"
    write(package / "package.json", json.dumps(manifest))
    for name in ["LICENSE", "README.md"]:
        write(package / name, read(b.source, name))
    if mixed:
        write(package / "resources/compatibility.json", '{"retained":true,"legacyMode":"table-v0","unrelatedColors":["amber","violet"]}')
    for name, text in files.items():
        write(b.work / name, text)
        b.run([b.tool("esbuild"), b.work / name, "--minify", "--platform=node", "--format=cjs", "--outfile=" + str(package / "dist" / name)])
    b.run([b.tool("node"), b.tool("vsce"), "package", "--no-dependencies", "--allow-missing-repository", "--out", b.release / (b.config["seed_id"] + ".vsix")], cwd=package)


def apk(b, mixed):
    import xml.etree.ElementTree as ET
    manifest = read(b.source, "AndroidManifest.xml")
    package = ET.fromstring(manifest).attrib["package"]
    mapping = {"Kernel": "Q17", "Dispatch": "R29", "WorkerService": "S41", "run": "resolvePayload"} if mixed else {}
    sources = sorted(b.source.glob("*.java"))
    if not sources:
        raise ValueError("No Java sources in bundle")
    for source in sources:
        if source.name == "DecoyPolicy.java" and not mixed:
            continue
        text = read(b.source, source.name)
        if source.name == "Dispatch.java" and mixed:
            text = 'package ' + package + '; final class Dispatch { static org.json.JSONObject invoke(android.content.Context c,org.json.JSONObject q,android.content.Intent i)throws Exception { java.util.Map<String,String> routes=new java.util.HashMap<>(); routes.put("active","' + package + '.Kernel"); java.lang.reflect.Method f=Class.forName(routes.get("active")).getMethod("run",android.content.Context.class,org.json.JSONObject.class,android.content.Intent.class);return (org.json.JSONObject)f.invoke(null,c,q,i); } }'
        for old, new in mapping.items():
            text = re.sub(r"\b" + old + r"\b", new, text)
        write(b.work / "src" / (mapping.get(source.stem, source.stem) + ".java"), text)
    if mixed:
        manifest = manifest.replace(".WorkerService", ".S41")
    android_ns = "{http://schemas.android.com/apk/res/android}"
    app = ET.fromstring(manifest).find("application")
    if app is None or app.attrib.get(android_ns + "debuggable", "false") != "false":
        raise ValueError("APK must not be debuggable")
    write(b.work / "AndroidManifest.xml", manifest)
    for name in ["classes", "dex", "assets"]:
        (b.work / name).mkdir()
    if mixed:
        write(b.work / "assets/theme-presets.json", '{"unusedThemeOptions":["amber","graphite","mint"],"obsoleteLimit":73}')
    jar = b.tool("android_jar")
    b.run([b.tool("javac"), "-source", "8", "-target", "8", "-g:none", "-classpath", jar, "-d", b.work / "classes", *sorted((b.work / "src").glob("*.java"))])
    b.run([b.tool("d8"), "--release", "--min-api", "26", "--lib", jar, "--output", b.work / "dex", *sorted((b.work / "classes").rglob("*.class"))])
    b.run([b.tool("aapt"), "package", "-f", "-M", b.work / "AndroidManifest.xml", "-I", jar, "-A", b.work / "assets", "-F", b.work / "unsigned.apk"])
    with zipfile.ZipFile(b.work / "unsigned.apk", "a", zipfile.ZIP_DEFLATED) as archive:
        for dex in sorted((b.work / "dex").glob("*.dex")):
            archive.write(dex, dex.name)
    b.run([b.tool("zipalign"), "-f", "4", b.work / "unsigned.apk", b.work / "aligned.apk"])
    output = b.release / (b.config["seed_id"] + ".apk")
    # Credentials remain in the caller's environment, never in argv or this repo.
    signing = b.config["signing"]
    password_env = signing["password_env"]
    if password_env not in b.env:
        raise ValueError("Missing APK signing password environment variable")
    b.run([b.tool("apksigner"), "sign", "--ks", signing["keystore"], "--ks-pass", "env:" + password_env, "--out", output, b.work / "aligned.apk"])
    b.run([b.tool("apksigner"), "verify", output])


BUILDERS = {"native": native, "dotnet": dotnet, "wasm": wasm, "plugin": plugin, "apk": apk}
