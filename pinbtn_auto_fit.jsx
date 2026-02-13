#target photoshop
app.bringToFront();

(function () {
  // ===== config 로딩 (Python이 %TEMP%에 pinbtn_config.json 생성) =====
  function readTextFile(f) { f.encoding="UTF8"; f.open("r"); var s=f.read(); f.close(); return s; }
  function parseJSON(s){ if(typeof JSON!=="undefined" && JSON.parse) return JSON.parse(s); return eval("(" + s + ")"); }

  var cfgFile = new File(Folder.temp.fsName + "/pinbtn_config.json");
  if (!cfgFile.exists) { alert("설정파일 없음: " + cfgFile.fsName); return; }
  var cfg = parseJSON(readTextFile(cfgFile));

  var templateFile = new File(cfg.template_psd);
  var inputFolder  = new Folder(cfg.input_dir);
  var outputFolder = new Folder(cfg.output_dir);
  var outPrefix    = cfg.output_prefix || "PINBUTTON_";
  var coverMargin  = (cfg.cover_margin_percent != null) ? cfg.cover_margin_percent : 3; // 3% 여유(재단/말림 대비)

  if (!templateFile.exists) { alert("템플릿 PSD 없음: " + templateFile.fsName); return; }
  if (!inputFolder.exists)  { alert("입력 폴더 없음: " + inputFolder.fsName); return; }
  if (!outputFolder.exists) { alert("출력 폴더 없음: " + outputFolder.fsName); return; }

  // ===== 유틸 =====
  function asPx(v) { return v.as("px"); }

  function boundsToRect(b){
    var l=asPx(b[0]), t=asPx(b[1]), r=asPx(b[2]), bb=asPx(b[3]);
    return {l:l, t:t, r:r, b:bb, w:(r-l), h:(bb-t), cx:(l+r)/2, cy:(t+bb)/2};
  }

  function findLayerByName(doc, name) {
    function walk(container) {
      for (var i=0; i<container.layers.length; i++){
        var lyr = container.layers[i];
        if (lyr.name === name) return lyr;
        if (lyr.typename === "LayerSet") {
          var found = walk(lyr);
          if (found) return found;
        }
      }
      return null;
    }
    return walk(doc);
  }

  function listImageFiles(folder) {
    var files = folder.getFiles(function (f) {
      if (!(f instanceof File)) return false;
      return f.name.toLowerCase().match(/\.(png|jpg|jpeg|tif|tiff|psd)$/);
    });
    files.sort(function(a,b){ return a.name.localeCompare(b.name); });
    return files;
  }

  // 가장 안정적인 “스마트오브젝트 내용 교체”
  function replaceSmartObjectContents(fileObj) {
    var id = stringIDToTypeID("placedLayerReplaceContents");
    var desc = new ActionDescriptor();
    desc.putPath(charIDToTypeID("null"), fileObj);
    executeAction(id, desc, DialogModes.NO);
  }

  // IMAGE_SO 레이어가 속한 “같은 부모(그룹)”에서 원형 기준 레이어(FILL_/MASK_) 찾기
  function findCircleRefLayer(imageLayer){
    var parent = imageLayer.parent; // LayerSet 또는 Document
    if (!parent || !parent.layers) return null;

    var best = null;
    var bestArea = 0;

    for (var i=0; i<parent.layers.length; i++){
      var lyr = parent.layers[i];
      var nm = lyr.name || "";
      if (nm.indexOf("FILL_") === 0 || nm.indexOf("MASK_") === 0) {
        try{
          var rect = boundsToRect(lyr.bounds);
          var area = rect.w * rect.h;
          // 원형이면 대체로 정사각형에 가까움 → 가로세로 비율 체크
          var ratio = rect.w > rect.h ? rect.w/rect.h : rect.h/rect.w;
          if (ratio < 1.2 && area > bestArea) { best = lyr; bestArea = area; }
        }catch(e){}
      }
    }
    return best; // 못 찾으면 null
  }

  // “원형을 꽉 채우기(COVER)” 스케일: layer의 긴 변이 원형 지름 이상이 되도록 확대
  function coverFitToCircle(imageLayer, circleRect){
    var imgRect = boundsToRect(imageLayer.bounds);

    // 목표 지름: circleRect의 더 긴 변(원형이면 거의 동일)
    var target = Math.max(circleRect.w, circleRect.h) * (1 + coverMargin/100.0);

    // 현재 이미지의 긴 변
    var cur = Math.max(imgRect.w, imgRect.h);
    if (cur <= 0) return;

    // 필요한 배율(%)
    var scalePct = (target / cur) * 100.0;

    // 작아도 키우고, 커도 “줄이고 싶으면” 아래 조건 제거하면 됨
    // 지금은 "꽉 채우기"가 목적이라 크면 그대로 두고 싶을 때가 많아서,
    // 원하면 항상 맞추도록 scalePct를 그냥 적용해도 됨.
    imageLayer.resize(scalePct, scalePct, AnchorPosition.MIDDLECENTER);

    // 원형 중심으로 이동
    var afterRect = boundsToRect(imageLayer.bounds);
    imageLayer.translate(circleRect.cx - afterRect.cx, circleRect.cy - afterRect.cy);
  }

  // ===== 실행 =====
  var doc = app.open(templateFile);
  var oldRuler = app.preferences.rulerUnits;
  app.preferences.rulerUnits = Units.PIXELS;

  try {
    var imgs = listImageFiles(inputFolder);
    if (imgs.length === 0) { alert("입력 폴더에 이미지가 없습니다."); return; }

    for (var i=1; i<=11; i++){
      var layerName = "IMAGE_SO" + i;
      var layer = findLayerByName(doc, layerName);
      if (!layer) continue;
      if (layer.typename !== "ArtLayer") continue;
      if (layer.kind !== LayerKind.SMARTOBJECT) continue;

      var imgFile = imgs[i-1];
      if (!imgFile) break;

      // 원형 기준 레이어 찾기(같은 그룹 내 FILL_/MASK_)
      var circleRef = findCircleRefLayer(layer);
      // 못 찾으면: 현재 레이어 위치(센터) 기준만 유지
      var circleRect = circleRef ? boundsToRect(circleRef.bounds) : boundsToRect(layer.bounds);

      // 교체
      doc.activeLayer = layer;
      replaceSmartObjectContents(imgFile);

      // “원형 기준 꽉 채우기 + 중앙정렬”
      coverFitToCircle(layer, circleRect);
    }

    function stamp(){
      var d = new Date();
      function z(n){ return (n<10?"0":"")+n; }
      return d.getFullYear()+z(d.getMonth()+1)+z(d.getDate())+"_"+z(d.getHours())+z(d.getMinutes())+z(d.getSeconds());
    }

    var outFile = new File(outputFolder.fsName + "/" + outPrefix + stamp() + ".psd");
    var psdOpt = new PhotoshopSaveOptions();
    psdOpt.layers = true;
    psdOpt.embedColorProfile = true;
    doc.saveAs(outFile, psdOpt, true, Extension.LOWERCASE);

  } catch (e) {
    alert("오류: " + e.message);
  } finally {
    app.preferences.rulerUnits = oldRuler;
  }
})();
