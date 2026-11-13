import { Dialog } from "../../components/ui/Dialog";

const shortcuts = [
  ["选中元素后", "方向键", "移动元素 1 像素"],
  ["选中元素后", "Shift + 方向键", "移动元素 10 像素"],
  ["选中文字框后", "+ / −", "增大／减小字号，范围 8～72"],
  ["选中文字或原位编辑", "Ctrl + ↑ / ↓", "增大／减小字号；中文组词时不触发"],
  ["原位编辑文字", "Enter", "插入换行"],
  ["原位编辑文字", "Ctrl + Enter", "完成文字输入，也可点击其他区域完成"],
  ["原位编辑文字", "Esc", "撤销本次文字输入并退出编辑"],
  ["取色期间", "右键 / Esc", "退出取色，不提交悬停颜色"],
  ["查看弹窗", "Esc", "关闭弹窗，返回工作台"],
];

export function ShortcutGuide({ close }: { close: () => void }) {
  return <Dialog title="快捷键与操作说明" close={close}>
    <p className="shortcut-intro">先点击画布选中图片或文字。键盘移动和字号快捷键在画布获得焦点后生效；文本输入框保留正常输入行为。</p>
    <div className="shortcut-list">
      {shortcuts.map(([scope, keys, action]) => <div className="shortcut-row" key={scope + keys}>
        <span><strong>{action}</strong><small>{scope}</small></span><kbd>{keys}</kbd>
      </div>)}
    </div>
    <h3 className="gesture-heading">鼠标与触控</h3>
    <ul className="gesture-list">
      <li>图片区域滚轮：围绕指针缩放框内图片，范围 25%～400%。</li>
      <li>图片放大超过 100% 后，按住左键或手指拖动图片内容调整取景；边框保持不动。</li>
      <li>拖动图片边框，或按住 Shift 拖动图片：移动整个图片框。</li>
      <li>拖动文字框移动；拖动元素右下角调整尺寸；双击文字框直接编辑。</li>
      <li>取色时点击或触摸松手确认颜色。文字始终在图片上方，可叠在图片上；添加文字不会缩小已有图片。</li>
      <li>工具栏可分别一键清空图片或文字；属性区可选中被其他图片遮挡的图层。</li>
    </ul>
  </Dialog>;
}
