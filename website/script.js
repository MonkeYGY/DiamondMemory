// Mobile Menu Toggle
function toggleMobileMenu() {
  const menu = document.getElementById('mobile-menu');
  menu.classList.toggle('active');
}

function closeMobileMenu() {
  const menu = document.getElementById('mobile-menu');
  menu.classList.remove('active');
}

// Check login state on page load
window.addEventListener('DOMContentLoaded', function() {
  const DOWNLOADS = {
    macArm64: 'https://github.com/MonkeYGY/diamondmemory-setup/releases/download/V1.0.0/-1.0.0-mac-arm64.dmg',
    macX64: 'https://github.com/MonkeYGY/diamondmemory-setup/releases/download/V1.0.0/-1.0.0-mac-x64.dmg',
    win: 'https://github.com/MonkeYGY/diamondmemory-setup/releases/download/V1.0.0/-1.0.0-setup.exe'
  };

  const COMMUNITY = {
    douyinUrl: 'https://www.douyin.com/user/MS4wLjABAAAAqzQPR0Ee1VN4BZhkQ615g2FTzBQmkCp-pYQjpearNqzG0_tmF-hlX2LAgCQ6mFw7?from_tab_name=main',
    groupHelpUrl: ''
  };

  const lightbox = document.getElementById('lightbox');
  const lightboxImg = document.getElementById('lightbox-img');
  const lightboxClose = document.getElementById('lightbox-close');

  // Download buttons
  document.getElementById('mac-download').addEventListener('click', function(e) {
    e.preventDefault();
    const modal = document.getElementById('mac-download-modal');
    if (!modal) {
      if (!DOWNLOADS.macArm64) {
        alert('macOS 下载链接尚未配置，请稍后再试。');
        return;
      }
      window.open(DOWNLOADS.macArm64, '_blank', 'noopener,noreferrer');
      return;
    }
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
  });
  
  document.getElementById('win-download').addEventListener('click', function(e) {
    e.preventDefault();
    if (!DOWNLOADS.win) {
      alert('Windows 下载链接尚未配置，请稍后再试。');
      return;
    }
    window.open(DOWNLOADS.win, '_blank', 'noopener,noreferrer');
  });

  const macModal = document.getElementById('mac-download-modal');
  const macModalClose = document.getElementById('mac-download-modal-close');
  const macArm64Btn = document.getElementById('mac-download-arm64');
  const macX64Btn = document.getElementById('mac-download-x64');

  function closeMacModal() {
    if (!macModal) return;
    macModal.classList.remove('active');
    macModal.setAttribute('aria-hidden', 'true');
  }

  if (macArm64Btn) {
    macArm64Btn.addEventListener('click', function(e) {
      e.preventDefault();
      if (!DOWNLOADS.macArm64) return;
      window.open(DOWNLOADS.macArm64, '_blank', 'noopener,noreferrer');
      closeMacModal();
    });
  }

  if (macX64Btn) {
    macX64Btn.addEventListener('click', function(e) {
      e.preventDefault();
      if (!DOWNLOADS.macX64) return;
      window.open(DOWNLOADS.macX64, '_blank', 'noopener,noreferrer');
      closeMacModal();
    });
  }

  if (macModalClose) {
    macModalClose.addEventListener('click', closeMacModal);
  }

  if (macModal) {
    macModal.addEventListener('click', function(e) {
      if (e.target === macModal) closeMacModal();
    });
  }

  const douyinLink = document.getElementById('douyin-link');
  if (douyinLink) {
    if (COMMUNITY.douyinUrl) {
      douyinLink.href = COMMUNITY.douyinUrl;
    }
    douyinLink.addEventListener('click', function(e) {
      if (!COMMUNITY.douyinUrl) {
        e.preventDefault();
        alert('抖音链接尚未配置。');
        return;
      }
    });
  }

  const groupLink = document.getElementById('group-link');
  if (groupLink) {
    groupLink.addEventListener('click', function(e) {
      if (!COMMUNITY.groupHelpUrl) {
        e.preventDefault();
        alert('请先进入抖音主页，在主页内点击群聊入口加入交流群。');
        return;
      }
      groupLink.href = COMMUNITY.groupHelpUrl;
    });
  }
  
  document.querySelectorAll('.screenshot-media').forEach(container => {
    const img = container.querySelector('img');
    if (img) {
      img.addEventListener('error', function() {
        container.classList.add('is-missing');
      });
      if (!img.complete || img.naturalWidth === 0) {
        img.loading = 'lazy';
      }
    }

    container.addEventListener('click', function() {
      const src = container.getAttribute('data-lightbox-src') || '';
      const alt = container.getAttribute('data-lightbox-alt') || '';
      if (!src || !lightbox || !lightboxImg) return;
      lightboxImg.src = src;
      lightboxImg.alt = alt;
      lightbox.classList.add('active');
      lightbox.setAttribute('aria-hidden', 'false');
    });
  });

  function closeLightbox() {
    if (!lightbox || !lightboxImg) return;
    lightbox.classList.remove('active');
    lightbox.setAttribute('aria-hidden', 'true');
    lightboxImg.src = '';
  }

  if (lightboxClose) {
    lightboxClose.addEventListener('click', closeLightbox);
  }

  if (lightbox) {
    lightbox.addEventListener('click', function(e) {
      if (e.target === lightbox) closeLightbox();
    });
  }

  window.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeLightbox();
  });

  // Feature cards click to show details
  document.querySelectorAll('.feature-card').forEach(card => {
    card.addEventListener('click', function() {
      this.classList.toggle('active');
    });
  });
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function(e) {
    const href = this.getAttribute('href');
    if (href !== '#' && document.querySelector(href)) {
      e.preventDefault();
      const target = document.querySelector(href);
      target.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }
  });
});

// Navbar scroll effect
let lastScroll = 0;
window.addEventListener('scroll', function() {
  const navbar = document.querySelector('.navbar');
  const currentScroll = window.pageYOffset;
  
  if (currentScroll > 50) {
    navbar.style.boxShadow = '0 4px 6px -1px rgba(0, 0, 0, 0.1)';
  } else {
    navbar.style.boxShadow = 'none';
  }
  
  lastScroll = currentScroll;
});
