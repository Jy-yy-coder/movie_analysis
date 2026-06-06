// ===== 游客身份系统 =====
function getGuestId() {
    let guestId = localStorage.getItem('guestId');
    if (!guestId) {
        guestId = 'guest_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('guestId', guestId);
    }
    return guestId;
}

// ===== 点赞功能 =====
function getLikedMovies() {
    const liked = localStorage.getItem('likedMovies');
    return liked ? JSON.parse(liked) : [];
}

function toggleLike(movieId) {
    movieId = String(movieId);
    let liked = getLikedMovies();
    const wasLiked = liked.includes(movieId);
    
    if (wasLiked) {
        liked = liked.filter(id => id !== movieId);
    } else {
        liked.push(movieId);
    }
    localStorage.setItem('likedMovies', JSON.stringify(liked));
    
    // 立即更新按钮状态
    updateActionButtons();
    
    // 添加动画效果
    const likeBtn = document.getElementById('like-btn');
    if (likeBtn) {
        likeBtn.style.transform = 'scale(1.1)';
        setTimeout(() => {
            likeBtn.style.transform = 'scale(1)';
        }, 200);
    }
    
    // 显示提示
    showNotification(wasLiked ? '已取消点赞' : '❤️ 点赞成功！');
    
    // 如果在个人中心页面，刷新列表
    if (document.getElementById('liked-list')) {
        renderProfile();
    }
}

function isLiked(movieId) {
    return getLikedMovies().includes(String(movieId));
}

// ===== 收藏功能 =====
function getCollectedMovies() {
    const collected = localStorage.getItem('collectedMovies');
    return collected ? JSON.parse(collected) : [];
}

function toggleCollect(movieId) {
    movieId = String(movieId);
    let collected = getCollectedMovies();
    const wasCollected = collected.includes(movieId);
    
    if (wasCollected) {
        collected = collected.filter(id => id !== movieId);
    } else {
        collected.push(movieId);
    }
    localStorage.setItem('collectedMovies', JSON.stringify(collected));
    
    // 立即更新按钮状态
    updateActionButtons();
    
    // 添加动画效果
    const collectBtn = document.getElementById('collect-btn');
    if (collectBtn) {
        collectBtn.style.transform = 'scale(1.1)';
        setTimeout(() => {
            collectBtn.style.transform = 'scale(1)';
        }, 200);
    }
    
    // 显示提示
    showNotification(wasCollected ? '已取消收藏' : '⭐ 收藏成功！');
    
    // 如果在个人中心页面，刷新列表
    if (document.getElementById('collected-list')) {
        renderProfile();
    }
}

function isCollected(movieId) {
    return getCollectedMovies().includes(String(movieId));
}

// ===== 显示通知提示 =====
function showNotification(message) {
    // 移除已有的通知
    const existing = document.querySelector('.notification');
    if (existing) existing.remove();
    
    // 创建新通知
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // 2秒后自动消失
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 2000);
}

// ===== 更新按钮显示状态 =====
function updateActionButtons() {
    const movieId = document.getElementById('movie-id')?.value;
    if (!movieId) return;
    
    // 更新点赞按钮
    const likeBtn = document.getElementById('like-btn');
    if (likeBtn) {
        if (isLiked(movieId)) {
            likeBtn.classList.add('active');
            likeBtn.innerHTML = '<i class="bi bi-heart-fill"></i> 已点赞';
        } else {
            likeBtn.classList.remove('active');
            likeBtn.innerHTML = '<i class="bi bi-heart"></i> 点赞';
        }
    }
    
    // 更新收藏按钮
    const collectBtn = document.getElementById('collect-btn');
    if (collectBtn) {
        if (isCollected(movieId)) {
            collectBtn.classList.add('active');
            collectBtn.innerHTML = '<i class="bi bi-star-fill"></i> 已收藏';
        } else {
            collectBtn.classList.remove('active');
            collectBtn.innerHTML = '<i class="bi bi-star"></i> 收藏';
        }
    }
}

// ===== 渲染个人中心 =====
function renderProfile() {
    const likedList = document.getElementById('liked-list');
    const collectedList = document.getElementById('collected-list');
    
    if (likedList) {
        renderMovieList(likedList, getLikedMovies(), '暂无点赞的电影');
    }
    if (collectedList) {
        renderMovieList(collectedList, getCollectedMovies(), '暂无收藏的电影');
    }
}

function renderMovieList(container, movieIds, emptyMsg) {
    if (movieIds.length === 0) {
        container.innerHTML = `<div class="col-12 text-center text-muted py-5">${emptyMsg}</div>`;
        return;
    }
    
    // 获取所有电影数据
    fetch('/api/movies')
        .then(r => r.json())
        .then(allMovies => {
            const movies = allMovies.filter(m => movieIds.includes(String(m.movie_id)));
            
            if (movies.length === 0) {
                container.innerHTML = `<div class="col-12 text-center text-muted py-5">${emptyMsg}</div>`;
                return;
            }
            
            container.innerHTML = movies.map(m => `
                <div class="col-6 col-md-4 col-lg-3 col-xl-2">
                    <a href="/movie/${m.movie_id}" class="movie-card">
                        <div class="poster-wrap">
                            <img src="${posterUrl(m.海报)}" alt="${m.片名}" loading="lazy">
                        </div>
                        <div class="card-body">
                            <div class="card-title">${m.片名}</div>
                            <div class="d-flex align-items-center gap-1 mb-1">
                                <span style="font-size:0.75rem;color:var(--text-muted)">${m.年份}年</span>
                                <span style="font-size:0.75rem;color:var(--text-muted)">·</span>
                                <span style="font-size:0.75rem;color:var(--text-muted)">${m.评论数}条</span>
                            </div>
                            <div class="card-meta">
                                <span class="score">${m.豆瓣评分}</span>
                                ${labelBadge(m.label, m.label_type)}
                            </div>
                        </div>
                    </a>
                </div>
            `).join('');
        });
}

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', function() {
    getGuestId();
    
    // 如果在电影详情页，更新按钮状态
    if (document.getElementById('movie-id')) {
        updateActionButtons();
    }
    
    // 如果在个人中心页面，渲染列表
    if (document.getElementById('liked-list') || document.getElementById('collected-list')) {
        renderProfile();
    }
});
