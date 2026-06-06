// 烟花动画
(function() {
    const canvas = document.createElement('canvas');
    canvas.id = 'fireworks-canvas';
    canvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0';
    
    const hero = document.querySelector('.hero-section');
    if (!hero) return;
    hero.insertBefore(canvas, hero.firstChild);
    
    const ctx = canvas.getContext('2d');
    let particles = [];
    let rockets = [];
    
    function resize() {
        canvas.width = hero.offsetWidth;
        canvas.height = hero.offsetHeight;
    }
    resize();
    window.addEventListener('resize', resize);
    
    // 火箭
    class Rocket {
        constructor() {
            this.x = Math.random() * canvas.width;
            this.y = canvas.height;
            this.targetY = Math.random() * canvas.height * 0.5 + 50;
            this.speed = 4 + Math.random() * 3;
            this.color = `hsl(${Math.random() * 60 + 20}, 100%, 60%)`;
            this.trail = [];
            this.exploded = false;
        }
        
        update() {
            this.y -= this.speed;
            this.trail.push({x: this.x, y: this.y, alpha: 1});
            if (this.trail.length > 10) this.trail.shift();
            
            if (this.y <= this.targetY && !this.exploded) {
                this.explode();
                this.exploded = true;
            }
        }
        
        explode() {
            const count = 40 + Math.floor(Math.random() * 30);
            for (let i = 0; i < count; i++) {
                const angle = (Math.PI * 2 / count) * i;
                const speed = 1 + Math.random() * 3;
                particles.push(new Particle(this.x, this.y, angle, speed, this.color));
            }
        }
        
        draw() {
            // 尾焰
            for (let i = 0; i < this.trail.length; i++) {
                const t = this.trail[i];
                ctx.beginPath();
                ctx.arc(t.x, t.y, 2, 0, Math.PI * 2);
                ctx.fillStyle = this.color.replace('60%)', '80%)').replace('hsl', 'hsla');
                ctx.globalAlpha = i / this.trail.length;
                ctx.fill();
            }
            ctx.globalAlpha = 1;
        }
    }
    
    // 粒子
    class Particle {
        constructor(x, y, angle, speed, color) {
            this.x = x;
            this.y = y;
            this.vx = Math.cos(angle) * speed;
            this.vy = Math.sin(angle) * speed;
            this.alpha = 1;
            this.decay = 0.01 + Math.random() * 0.02;
            this.color = color;
            this.size = 1.5 + Math.random() * 1.5;
        }
        
        update() {
            this.x += this.vx;
            this.y += this.vy;
            this.vy += 0.05; // 重力
            this.vx *= 0.98; // 阻力
            this.alpha -= this.decay;
        }
        
        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fillStyle = this.color;
            ctx.globalAlpha = this.alpha;
            ctx.fill();
            ctx.globalAlpha = 1;
        }
    }
    
    // 发射烟花
    function launch() {
        rockets.push(new Rocket());
        setTimeout(launch, 800 + Math.random() * 1500);
    }
    
    // 动画循环
    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // 更新火箭
        rockets = rockets.filter(r => !r.exploded || r.trail.length > 0);
        rockets.forEach(r => {
            r.update();
            r.draw();
        });
        
        // 更新粒子
        particles = particles.filter(p => p.alpha > 0);
        particles.forEach(p => {
            p.update();
            p.draw();
        });
        
        requestAnimationFrame(animate);
    }
    
    // 启动
    setTimeout(launch, 500);
    animate();
})();
