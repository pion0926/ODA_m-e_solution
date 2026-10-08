import init, {HwpDocument} from './core/0.8.6/rhwp.js';
let document;
self.onmessage = async ({data}) => {
  try {
    if (data.type === 'open') {
      await init();
      document?.free();
      document = new HwpDocument(new Uint8Array(data.bytes));
      self.postMessage({id:data.id,result:document.pageCount()});
    } else if (data.type === 'page' && document) {
      if (!Number.isInteger(data.page) || data.page < 0 || data.page >= document.pageCount()) throw Error('유효하지 않은 쪽 번호');
      self.postMessage({id:data.id,result:document.renderPageSvg(data.page)});
    } else throw Error('문서를 먼저 열어 주세요.');
  } catch (error) {
    self.postMessage({id:data.id,error:error.message || String(error)});
  }
};
