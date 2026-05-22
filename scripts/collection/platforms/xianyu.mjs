export const xianyuProfile = Object.freeze({
  platform: "闲鱼",
  slug: "xianyu",
  mode: "probe",
  startUrl: "https://www.goofish.com/",
  defaultLimit: 3,
  bulkCollectionAllowed: false,
  probeChecklist: [
    "confirm login wall behavior",
    "identify search entry",
    "identify commodity cards",
    "open one item by simulated click",
    "extract stable public fields",
  ],
  extraFields: ["price", "location", "seller"],
});
