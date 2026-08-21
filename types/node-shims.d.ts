
declare const process: { pid: number }
declare module "node:crypto" { export const createHash: any }
declare module "node:fs" { export const constants: any }
declare module "node:fs/promises" { export const access: any; export const mkdir: any; export const open: any; export const readFile: any; export const rename: any; export const rm: any; export const stat: any; export const lstat: any; export const realpath: any; export const writeFile: any }
declare module "node:path" { const path: any; export default path }
declare module "node:timers/promises" { export const setTimeout: any }
