export const GRAPH_REFRESH_EVENT = 'dm:graph-refresh'

export function requestGraphRefresh() {
  window.dispatchEvent(new CustomEvent(GRAPH_REFRESH_EVENT))
}

