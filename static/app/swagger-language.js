const header = document.querySelector(".api-header");
document.documentElement.lang = header.lang;
if (header.lang === "fa") {
  // Translate Swagger controls only. Paths, schemas, examples and responses are API data.
  const labels = {
    "Authorize": "احراز هویت", "Authorized": "وارد شده", "Logout": "خروج",
    "Close": "بستن", "Cancel": "انصراف", "Execute": "اجرا", "Clear": "پاک کردن",
    "Try it out": "امتحان کنید", "Parameters": "پارامترها", "No parameters": "بدون پارامتر",
    "Request body": "بدنهٔ درخواست", "Responses": "پاسخ‌ها", "Code": "کد",
    "Description": "توضیحات", "Links": "پیوندها", "No links": "بدون پیوند",
    "Schemas": "ساختار داده‌ها", "Schema": "ساختار", "Example Value": "نمونه",
    "Media type": "نوع محتوا", "Name": "نام", "required": "الزامی", "Value:": "مقدار:",
    "Username:": "نام کاربری:", "Password:": "رمز عبور:", "Server response": "پاسخ سرور",
    "Response headers": "هدرهای پاسخ", "Request URL": "نشانی درخواست",
    "Response body": "بدنهٔ پاسخ", "Download": "دانلود", "Available authorizations": "روش‌های احراز هویت",
    "Response content type": "نوع محتوای پاسخ", "Controls Accept header.": "هدر Accept را تنظیم می‌کند."
  };
  function localize(root) {
    if (root.nodeType !== Node.ELEMENT_NODE || root.closest("pre,code,textarea,.model,.response-col_description__inner")) return;
    for (const child of root.childNodes) {
      if (child.nodeType === Node.TEXT_NODE && Object.hasOwn(labels, child.textContent.trim())) {
        child.textContent = labels[child.textContent.trim()];
      } else if (child.nodeType === Node.ELEMENT_NODE) localize(child);
    }
  }
  const ui = document.getElementById("swagger-ui");
  localize(ui);
  new MutationObserver(records => {
    for (const record of records) for (const node of record.addedNodes) localize(node);
  }).observe(ui, {childList: true, subtree: true});
}
