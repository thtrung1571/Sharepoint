"""SharePoint DOM selectors and library constants."""

TARGET_URL = (
    "https://alltech-my.sharepoint.com/personal/nle_alltech_com/"
    "_layouts/15/onedrive.aspx?e=5%3Adeb6c80782104c409aa3407e580ef1ba"
    "&sharingv2=true&fromShare=true&at=9"
    "&CID=3d134348%2Da0e4%2D4f09%2Db0b1%2D576c4052d34e"
    "&id=%2Fpersonal%2Fnle%5Falltech%5Fcom%2FDocuments%2FNgoc%20Nga%20Documents%20%2D%20PDMM%2FPDMM%2F3%2E%20DOMESTIC%2FDOMESTIC%2FDomestic%20%2D2026%2FVI%E1%BB%86T%20%C3%82U"
    "&FolderCTID=0x012000357D47895F012E4FA6DB93BD359D1324&view=0"
)

BASE_ID = (
    "%2Fpersonal%2Fnle%5Falltech%5Fcom%2FDocuments%2FNgoc%20Nga%20Documents%20%2D%20PDMM"
    "%2FPDMM%2F3%2E%20DOMESTIC%2FDOMESTIC%2FDomestic%20%2D2026%2FVI%E1%BB%86T%20%C3%82U"
)


class Selectors:
    """Central registry of SharePoint DOM selectors."""

    ACCOUNT_TILE = "//div[@data-bind='text: session.tileDisplayName']"
    EMAIL_INPUT = '//input[@type="email"]'
    SUBMIT_BUTTON = '//input[@id="idSIButton9"]'
    OTC_INPUT = '//*[@id="idTxtBx_OTC_Password"]'
    OTC_ERROR = "//*[@id='idTd_OTCC_Error_OTC']"
    LIST_CONTAINER = '//*[@id="html-list_3"]'
    EMPTY_PLACEHOLDER = "//div[@data-automationid='list-empty-placeholder-title']"
    ROW = "[data-automationid^='row-']"
    FILENAME_FIELD = "[data-automationid='field-LinkFilename']"
    DOWNLOAD_BUTTON = "//button[@data-automationid='downloadCommand']"
    BREADCRUMB_ITEM = "[data-automationid='breadcrumb-listitem']"
    BREADCRUMB_CRUMB = "[data-automationid='breadcrumb-crumb']"
