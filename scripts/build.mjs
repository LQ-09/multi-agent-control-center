import * as esbuild from 'esbuild';
import {mkdir,writeFile} from 'node:fs/promises';
const dev=process.argv.includes('--serve');
await mkdir('dist',{recursive:true});
await writeFile('dist/index.html','<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#111716"><title>Agent Control Center</title><link rel="stylesheet" href="/app.css"></head><body><div id="root"></div><script type="module" src="/app.js"></script></body></html>');
const options={entryPoints:['src/main.tsx'],bundle:true,outfile:'dist/app.js',format:'esm',platform:'browser',target:'es2022',jsx:'automatic',minify:!dev,sourcemap:dev,define:{'process.env.NODE_ENV':JSON.stringify(dev?'development':'production')}};
if(dev){const ctx=await esbuild.context(options);await ctx.watch();await ctx.serve({host:'127.0.0.1',port:1420,servedir:'dist'});console.log('Native app development assets: http://127.0.0.1:1420 (no backend/browser dashboard)');}
else await esbuild.build(options);
