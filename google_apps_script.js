/**
 * =================================================================
 * TELEGRAM AI AGENT — GOOGLE SHEETS DASHBOARD & AVTO-JURNAL
 * =================================================================
 * 
 * Ushbu skript Google Sheets ichida ikkita varaq (tab) yaratadi:
 * 1. "📊 Dashboard" — Jami postlar, o'rtacha ball va kategoriyalar statistikasi.
 * 2. "📝 Postlar Jurnali" — Har bir kelgan videoning to'liq tahlili.
 */

function doPost(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var journalSheet = ss.getSheetByName("📝 Postlar Jurnali");
    var dashboardSheet = ss.getSheetByName("📊 Dashboard");

    // 1. Agar "Postlar Jurnali" varag'i bo'lmasa yaratish
    if (!journalSheet) {
      journalSheet = ss.insertSheet("📝 Postlar Jurnali");
      journalSheet.appendRow([
        "Sana va Vaqt",
        "Manba Kanal",
        "Xabar ID",
        "Format",
        "Kategoriya",
        "Final Ball (0-100)",
        "Holat",
        "Qaror / Sabab",
        "Yaratilgan Post Matni"
      ]);
      journalSheet.getRange("A1:I1")
        .setFontWeight("bold")
        .setBackground("#0f172a")
        .setFontColor("#ffffff")
        .setHorizontalAlignment("center");
      journalSheet.setFrozenRows(1);
    }

    // 2. Agar "Dashboard" varag'i bo'lmasa yaratish
    if (!dashboardSheet) {
      dashboardSheet = ss.insertSheet("📊 Dashboard", 0);
      setupDashboard(dashboardSheet);
    }

    // 3. Ma'lumotni qabul qilish
    var data = JSON.parse(e.postData.contents);
    var status = data.status || "NEW";
    var score = data.final_score || 0;

    // 4. Jurnalga yangi qator yozish
    journalSheet.appendRow([
      data.timestamp || new Date().toLocaleString("uz-UZ"),
      data.source_channel || "",
      data.source_message_id || "",
      (data.media_type || "media").toUpperCase(),
      data.category || "General",
      score,
      status,
      data.reason || "",
      data.caption || ""
    ]);

    var lastRow = journalSheet.getLastRow();
    
    // Holat ustunini ranglash (POSTED -> Yashil, REJECTED -> Qizil)
    var statusCell = journalSheet.getRange(lastRow, 7);
    if (status === "POSTED") {
      statusCell.setBackground("#dcfce7").setFontColor("#15803d").setFontWeight("bold");
    } else if (status === "REJECTED") {
      statusCell.setBackground("#fee2e2").setFontColor("#b91c1c").setFontWeight("bold");
    } else {
      statusCell.setBackground("#fef3c7").setFontColor("#b45309").setFontWeight("bold");
    }

    // Ball ustunini markazlash
    journalSheet.getRange(lastRow, 6).setHorizontalAlignment("center").setFontWeight("bold");

    return ContentService.createTextOutput(JSON.stringify({ "result": "success", "row": lastRow }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({ "result": "error", "error": error.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function setupDashboard(sheet) {
  sheet.clear();
  sheet.getRange("B2:G2").merge().setValue("🤖 AUTONOMOUS AI MEDIA CREATOR — DASHBOARD")
    .setFontWeight("bold").setFontSize(16).setBackground("#1e293b").setFontColor("#ffffff").setHorizontalAlignment("center");

  // KPI Kartochkalari
  sheet.getRange("B4").setValue("📥 Jami Tahlil Qilingan").setFontWeight("bold");
  sheet.getRange("B5").setFormula("=COUNTA('📝 Postlar Jurnali'!A2:A)").setFontSize(20).setFontWeight("bold").setHorizontalAlignment("center");

  sheet.getRange("D4").setValue("✅ Joylangan (Posted)").setFontWeight("bold");
  sheet.getRange("D5").setFormula('=COUNTIF(\'📝 Postlar Jurnali\'!G2:G, "POSTED")').setFontSize(20).setFontWeight("bold").setFontColor("#16a34a").setHorizontalAlignment("center");

  sheet.getRange("F4").setValue("⛔️ Rad Etilgan (Rejected)").setFontWeight("bold");
  sheet.getRange("F5").setFormula('=COUNTIF(\'📝 Postlar Jurnali\'!G2:G, "REJECTED")').setFontSize(20).setFontWeight("bold").setFontColor("#dc2626").setHorizontalAlignment("center");

  // O'rtacha ball
  sheet.getRange("B7").setValue("⭐ O'rtacha Sifat Bali").setFontWeight("bold");
  sheet.getRange("B8").setFormula("=AVERAGE('📝 Postlar Jurnali'!F2:F)").setFontSize(20).setFontWeight("bold").setFontColor("#2563eb").setHorizontalAlignment("center");

  sheet.getRange("B4:G5").setBackground("#f8fafc").setBorder(true, true, true, true, true, true);
  sheet.getRange("B7:D8").setBackground("#f8fafc").setBorder(true, true, true, true, true, true);
}
