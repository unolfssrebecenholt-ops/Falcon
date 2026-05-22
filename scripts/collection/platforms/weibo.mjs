export const weiboProfile = Object.freeze({
  platform: "微博",
  slug: "weibo",
  mode: "probe",
  startUrl: "https://weibo.com/",
  defaultLimit: 3,
  bulkCollectionAllowed: false,
  probeChecklist: [
    "confirm login wall behavior",
    "identify search entry",
    "handle expand-full-text control",
    "extract repost/comment/like counts",
    "extract up to nine image assets",
  ],
  extraFields: ["author", "repost_count"],
});
