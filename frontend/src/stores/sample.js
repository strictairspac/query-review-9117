import{listSamples}from'../api/sample.js';export const samples={items:[],async load(){this.items=await listSamples();return this.items}};
