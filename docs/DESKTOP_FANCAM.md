# macOS Fancam 实验分支

本分支保存 Stage Lab 的 macOS 命令行成员直拍实验。输入本机视频，选定开场成员，生成 9:16 预览；当前没有独立桌面 GUI，也没有通过稳定锁人效果验收。iOS 和云端改动不属于本次提交。

## 本机运行环境

使用 Python 3.11、FFmpeg，以及 `.local-ai/venv` 内现有推理环境。模型位置和哈希见 `backend/workers/analysis/model-manifest.json`；基础环境的准备流程见 `scripts/bootstrap-local-ai.sh`。视频、权重、特征和本机标注不随代码发布。

Fancam 的直接依赖记录在 worker 的 `fancam` 可选依赖中。已有基础推理环境可安装 `backend/workers/analysis[fancam]`；新机器的 OpenMMLab 环境仍需上述 bootstrap 的平台编译流程，不能只安装这个可选依赖。

EdgeTAM 入口另需本机独立 checkout（本次运行基于 `facebookresearch/EdgeTAM` 的 `7711e012a30a2402c4eaab637bdb00a521302c91`）及 `edgetam.pt`。现有运行目录为 `.local-ai/EdgeTAM`、`.local-ai/edgetam-deps`；其 `sam2` 模块及配置由 checkout 提供。该可选运行环境尚未合入基础哈希锁或制作安装包；代码分支不代表开箱即用的桌面发行版。

## 生成离线 B 预览

从仓库根目录运行，替换视频绝对路径和新输出文件名。B 表示开场从左到右第二位；固定五人要求开场完整同框。输出文件必须不存在。

```bash
rtk proxy env PYTHONPATH=.local-ai/edgetam-deps:.local-ai/EdgeTAM:backend/workers/analysis \
  .local-ai/venv/bin/python -m stage_lab_analysis.fancam_demo.edgetam_preview_cli \
  --source /absolute/path/input.mp4 \
  --checkpoint .local-ai/EdgeTAM/checkpoints/edgetam.pt \
  --output .local-ai/fancam-previews/B-new-preview.mp4 \
  --duration 30 --member B --members 5 --sample-fps 10 --device cpu \
  --identity-fusion --wholebody --offline-trajectories \
  --reseed-on-reacquire --absence-hold-seconds 0.5
```

`--offline-trajectories` 保留真实弱检测节点，使用匿名双向轨迹及同身份两端锚点恢复中间路径。推断节点不学习身份库、不触发蒙版重提示。镜头平移必须改善人物框外的背景对齐；证据不足保持未知。缺席超过 .5 秒时回全景。

## 验证和限制

```bash
rtk proxy env PYTHONPATH=backend/workers/analysis .local-ai/venv/bin/python \
  -m pytest backend/workers/analysis/tests -q -p no:cacheprovider
rtk proxy ffmpeg -v error -nostdin -i .local-ai/fancam-previews/B-new-preview.mp4 -f null -
```

通过测试或完整解码仅证明自动逻辑及媒体有效，不证明身份准确或成片达标。必须另外核对全片是否始终为同一成员、可见时保留头脚、取景大小稳定，以及后排和短遮挡是否无必要地回全景。

目前身份特征质量不足、匿名路径缺锚点、交叉遮挡和镜头缩放仍可能导致回退。局部背景补偿改善不等于身份恢复成功。当前阶段和实际全片结果见 `PROJECT_STATUS.md`，已确认限制见 `KNOWN_ISSUES.md`。
