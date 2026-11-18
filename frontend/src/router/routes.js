export const routes=[['samples','01','样本库'],['review','02','SQL 复核'],['history','03','运行历史'],['evidence','04','证据详情']];export const current=()=>location.hash.slice(1).split('/')[0]||'samples';
