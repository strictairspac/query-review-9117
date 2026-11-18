import{api,post}from'./client.js';export const listBatches=()=>api('/batches');export const createBatch=data=>post('/batches',data);
