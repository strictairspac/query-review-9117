import{listEvidence}from'../api/evidence.js';export const evidence={items:[],async load(){this.items=await listEvidence();return this.items}};
