import{STATUSES}from'../../constants/enums.js';import{esc}from'../../utils/html.js';export const badge=s=>'<span class="badge '+esc(s)+'">'+esc(STATUSES[s]||s)+'</span>';
