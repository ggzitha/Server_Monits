#!/usr/bin/env python3
"""
build_frontend.py - Single Source of Truth TypeScript Transpiler

Uses Node.js v22+ native `stripTypeScriptTypes` to compile all modules in
`frontend/src/` into 100% syntactically valid ES modules in `backend/app/static/js/editor/`.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "frontend" / "src"
OUT_DIR = ROOT_DIR / "backend" / "app" / "static" / "js" / "editor"


def find_node_binary() -> str:
    which_node = shutil.which("node")
    if which_node:
        return which_node
    candidates = [
        Path(r"C:\Program Files\Adobe\Adobe Photoshop 2026\node.exe"),
        Path(r"C:\Program Files\nodejs\node.exe"),
        Path(r"C:\Users\kenconex\AppData\Local\Programs\node\node.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    raise RuntimeError("Node.js binary not found. Cannot transpile TypeScript.")


def build():
    node_exe = find_node_binary()
    print(f">> Using Node engine: {node_exe}")

    runner_script = ROOT_DIR / "scripts" / "_transpile_runner.mjs"
    runner_code = """
import fs from 'node:fs';
import path from 'node:path';
import { stripTypeScriptTypes } from 'node:module';

const srcDir = process.argv[2];
const outDir = process.argv[3];

function walk(dir) {
    let results = [];
    const list = fs.readdirSync(dir);
    list.forEach(file => {
        file = path.join(dir, file);
        const stat = fs.statSync(file);
        if (stat && stat.isDirectory()) {
            results = results.concat(walk(file));
        } else if (file.endsWith('.ts') && !file.endsWith('.d.ts') && !file.endsWith('.test.ts')) {
            results.push(file);
        }
    });
    return results;
}

const files = walk(srcDir);
let count = 0;

for (const f of files) {
    const raw = fs.readFileSync(f, 'utf8');
    const stripped = stripTypeScriptTypes(raw);
    const filename = path.basename(f, '.ts') + '.js';
    const outPath = path.join(outDir, filename);
    const header = `/**\\n * AUTO-GENERATED from frontend/src/${path.basename(f)}\\n * DO NOT EDIT DIRECTLY. Source of truth is TypeScript in frontend/src/.\\n */\\n`;
    fs.writeFileSync(outPath, header + stripped, 'utf8');
    console.log(`  Compiled: ${path.relative(srcDir, f)} -> ${filename}`);
    count++;
}

console.log(`\\nSuccessfully compiled ${count} TypeScript modules into standard ES modules.`);
"""
    runner_script.write_text(runner_code, encoding="utf-8")

    try:
        res = subprocess.run(
            [node_exe, str(runner_script), str(SRC_DIR), str(OUT_DIR)],
            check=True,
            capture_output=True,
            text=True,
        )
        print(res.stdout)
    finally:
        if runner_script.exists():
            runner_script.unlink()


if __name__ == "__main__":
    build()
