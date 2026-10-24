import {defineConfig, loadEnv} from 'vite';
import react from '@vitejs/plugin-react';
import {execFileSync} from 'node:child_process';
import {resolveApiBase} from './src/api.js';

export default defineConfig(({command,mode}) => {
  const env=loadEnv(mode,process.cwd(),'VITE_');
  const apiBase=resolveApiBase(process.env.VITE_API_BASE_URL || env.VITE_API_BASE_URL, command==='build');
  let revision='unavailable',dirty=true;
  try {
    revision=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
    dirty=Boolean(execFileSync('git',['status','--porcelain'],{encoding:'utf8'}).trim());
  } catch { /* Build packages may omit Git metadata. Never invent a revision. */ }
  return {plugins:[react(),{name:'cityhive-build-info',generateBundle(){
    this.emitFile({type:'asset',fileName:'build-info.json',source:JSON.stringify({application:'Cityhive',revision,dirty,apiBase},null,2)});
  }}],server:{proxy:{'/api':{target:process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',changeOrigin:true}}}};
});
