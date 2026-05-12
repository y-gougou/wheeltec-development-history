import React from 'react';
import { Wifi, WifiOff, Languages, Sun, Moon, Gamepad2 } from 'lucide-react';

export default function TopBar({ rosState, theme, onToggleTheme, lang, onToggleLang, gamepadConnected, t }) {
  return (
    <header className="topbar">
      <div>
        <h1>{t('title')}</h1>
        <p>{t('subtitle')}</p>
      </div>
      <div className="topbar-right">
        {gamepadConnected && (
          <div className="net online"><Gamepad2 size={15}/> PAD</div>
        )}
        <div className={`net ${rosState}`}>
          {rosState === 'online' ? <Wifi size={15}/> : <WifiOff size={15}/>}
          {t(rosState) || rosState}
        </div>
        <button className="icon-btn" onClick={onToggleLang} title="Language">
          <Languages size={16}/> {lang === 'zh' ? 'EN' : '中'}
        </button>
        <button className="icon-btn" onClick={onToggleTheme} title="Theme">
          {theme === 'dark' ? <Sun size={16}/> : <Moon size={16}/>}
        </button>
      </div>
    </header>
  );
}
