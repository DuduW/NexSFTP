# v1.8 变更记录（2026-10-13）— 安全整改

## 修复：存储型 XSS（WAPT 报告 CONFIRMED，CWE-79，P3）
- F1 输出转义（根因）：文件列表页文件名/路径全量 HTML 实体转义，三处注入上下文（元素体/内联属性/URL）分别处理
- F2 事件重构：文件名移入 data-* 属性 + addEventListener 事件委托，彻底移出内联 onclick；上传/退出按钮同步去内联
- F3 入口白名单（纵深）：Web 上传/rename + SFTP open(CREAT)/mkdir/rename 拒绝含 < > " ' 及控制字符的文件名（双面同规则）
- F4 CSP 兜底：/f/ 页面响应头 Content-Security-Policy: default-src 'self' + X-Content-Type-Options: nosniff
- 附带：页面 title 用户名转义；SFTP 拒绝入审计

## 验证
- 按报告 4.2 完整复现攻击链：Web 投毒 403/400 拦截、SFTP 投毒拒绝、绕过入口直落盘文件渲染为纯文本（&lt;img&gt; 实体）
- CSP/nosniff 头存在；内联 onclick 清零；负对照（中文名/只读账号/SFTP 正常写）不误伤
- 52 项全量回归 PASS 52/FAIL 0
