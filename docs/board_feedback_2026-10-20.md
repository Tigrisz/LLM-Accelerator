# B 的首次板端反馈记录

用户转发的 B 消息：

> 状态：1/1/0  
> 复位重跑结果：1/1/0

按前面请求的 done/pass/fail 顺序，解释为完成、通过、无错误；复位后再次通过。
此证据为 B 的文字反馈，不是本地工具采集或逐行输出读回。

用户同时提供的 `fixed_slice_qwen_demo_top.sbit` 与仓库
`fpgatest/qwen_slice/prj/generate_bitstream/fixed_slice_qwen_demo_top.sbit`
SHA-256 一致：

```text
1afcc84514b839d375aeef35b6fe9e2e07f995408cd3da883d1b96ea450ff96f
```

进度更新：固定 16×128 切片已获得 B 的板端自检通过及一次复位重跑反馈。
此前 integration_status_2026-10-20.md 中“待补板端状态”的事项获得这条后续证据，
无需将编程配置 done bit 当作计算通过的证明。

下一步请 B 提供逐行结果文件，格式见 result_capture_v1.md；
并补模型 checkpoint revision、切片 config 和量化 scale。上述文件不影响当前整数
结果比对，但影响来源追溯和后续反量化验证。
