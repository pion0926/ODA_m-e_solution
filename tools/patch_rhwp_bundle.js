const fs = require("fs");
const path = require("path");

const bundlePath = path.join("assets", "rhwp", "assets", "index.js");
let text = fs.readFileSync(bundlePath, "utf8");

text = text.replaceAll("`/rhwp/`+e", "`/assets/rhwp/`+e");
text = text.replaceAll("`/rhwp/assets/rhwp_bg-DsnvX-Xj.wasm`", "`/assets/rhwp/assets/rhwp_bg-DsnvX-Xj.wasm`");

const marker = "case`exportHwpVerify`:await Nd,a(JSON.parse(X.exportHwpVerify()));break;default:";
const injected = "case`exportHwpVerify`:await Nd,a(JSON.parse(X.exportHwpVerify()));break;case`searchAllText`:await Nd,a(X.searchAllText(i?.query??i?.text??``,!!i?.caseSensitive,!!i?.includeCells));break;case`replaceAll`:await Nd;{let e=X.replaceAll(i?.query??``,i?.newText??i?.value??``,!!i?.caseSensitive);Q?.loadDocument(),nd.markDirty(`api-replaceAll`),Z.emit(`document-changed`,`api-replaceAll`),a(e)}break;case`replaceText`:await Nd;{let e=X.replaceText(i?.sec??i?.sectionIndex??0,i?.para??i?.paragraphIndex??0,i?.charOffset??0,i?.length??0,i?.newText??i?.text??``);Q?.loadDocument(),nd.markDirty(`api-replaceText`),Z.emit(`document-changed`,`api-replaceText`),a(e)}break;case`insertText`:await Nd;{let e=X.insertText(i?.sec??i?.sectionIndex??0,i?.para??i?.paragraphIndex??0,i?.charOffset??0,i?.text??``);Q?.loadDocument(),nd.markDirty(`api-insertText`),Z.emit(`document-changed`,`api-insertText`),a(e)}break;case`getFieldList`:await Nd,a(X.getFieldList());break;case`setFieldValueByName`:await Nd;{let e=X.setFieldValueByName(i?.name??``,i?.value??``);Q?.loadDocument(),nd.markDirty(`api-setFieldValueByName`),Z.emit(`document-changed`,`api-setFieldValueByName`),a(e)}break;case`setFieldValue`:await Nd;{let e=X.setFieldValue(i?.fieldId??0,i?.value??``);Q?.loadDocument(),nd.markDirty(`api-setFieldValue`),Z.emit(`document-changed`,`api-setFieldValue`),a(e)}break;default:";

if (!text.includes(marker)) {
  throw new Error("Could not find rhwp postMessage switch marker.");
}
text = text.replace(marker, injected);
fs.writeFileSync(bundlePath, text);
