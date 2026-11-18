import{api,post}from'./client.js';export const listSamples=()=>api('/samples');export const createSample=data=>post('/samples',data);
