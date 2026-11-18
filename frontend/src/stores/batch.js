import{listBatches}from'../api/batch.js';export const batches={items:[],async load(){this.items=await listBatches();return this.items}};
