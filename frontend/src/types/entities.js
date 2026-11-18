/** @typedef {{id:number,name:string,description:string,original_sql:string}} Sample */
/** @typedef {{id:number,name:string,sample_id:number,candidate_sql:string,status:string}} Batch */
/** @typedef {{id:number,batch_id:number,result:Object}} Evidence */
export const entityNames={sample:'SQL 样本',batch:'复核批次',evidence:'执行证据'};
