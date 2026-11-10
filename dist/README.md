# dist/web —— 临时投递目录

公网服务器的镜像链路只有 ~120 KB/s，而一次前端更新里 68 MB 的发布包里
只有 `main.dart.js`（3.3 MB）真的变了，其余是两千多张没动的菜图。

所以需要单文件热更时，把 CI 产物里的 `main.dart.js` 放这里，用 CDN 直接
拉到服务器的 `/opt/web/main.dart.js`，省掉 65 MB 的重复传输。

**这不是构建产物仓库**，只是一条应急通道。下次正式部署（deploy.sh
--web-from-release）后可以整个删掉。
