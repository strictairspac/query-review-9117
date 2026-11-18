import{listSpeedTests}from'../api/speedTest.js';export const speedTests={items:[],async load(batchId){this.items=await listSpeedTests(batchId);return this.items}};
