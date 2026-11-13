/** 阻尼弹簧保留当前位置与速度，连续输入只改变目标，不排队播放过时动画。 */
export class ScalarSpring {
  private velocity = 0;
  private target: number;
  private frame = 0;
  private last = 0;
  private rest?: () => void;

  constructor(private value: number, private update: (value: number) => void) {
    this.target = value;
  }

  to(target: number, rest?: () => void) {
    this.target = target;
    this.rest = rest;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || document.hidden) {
      this.finish();
      return;
    }
    if (!this.frame) {
      this.last = performance.now();
      this.frame = requestAnimationFrame(this.tick);
    }
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.frame = 0;
  }

  private finish() {
    this.dispose();
    this.velocity = 0;
    this.value = this.target;
    this.update(this.value);
    const callback = this.rest;
    this.rest = undefined;
    callback?.();
  }

  private tick = (time: number) => {
    if (document.hidden || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      this.finish();
      return;
    }
    let elapsed = Math.min((time - this.last) / 1000, 0.064);
    this.last = time;
    while (elapsed > 0) {
      const step = Math.min(elapsed, 1 / 120);
      this.velocity += (-600 * (this.value - this.target) - 38 * this.velocity) * step;
      this.value += this.velocity * step;
      elapsed -= step;
    }
    this.update(this.value);
    if (Math.abs(this.value - this.target) < 0.0002 && Math.abs(this.velocity) < 0.002) this.finish();
    else this.frame = requestAnimationFrame(this.tick);
  };
}
