export const douyinProfile = Object.freeze({
  platform: "抖音",
  slug: "douyin",
  mode: "probe",
  startUrl: "https://www.douyin.com/",
  defaultLimit: 3,
  bulkCollectionAllowed: false,
  probeChecklist: [
    "confirm login wall behavior",
    "identify search entry",
    "identify visible video cards",
    "open one public item by simulated click",
    "extract public metadata and cover only",
  ],
  assetPolicy: "download cover images only; do not download video files by default",
  extraFields: ["author", "music", "video_duration"],
});
