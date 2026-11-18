/** @typedef {{id:number,name:string,description:string,original_sql:string}} Sample */
/** @typedef {{id:number,name:string,sample_id:number,candidate_sql:string,status:string}} Batch */
/** @typedef {{id:number,batch_id:number,result:Object}} Evidence */
/** @typedef {{id:number,batch_id:number,status:string,rounds:Array,result:Object,elapsed_ms:number,created_at:string,finished_at:string|null}} SpeedTest */
export const entityNames={sample:'SQL 样本',batch:'复核批次',evidence:'执行证据',speedTest:'提速复测'};
