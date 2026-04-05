import { motion } from "framer-motion";
import { useMemo } from "react";
import { Music } from "lucide-react";

// Get the letter for a bingo number
const getLetterForNumber = (num) => {
  if (num <= 15) return "B";
  if (num <= 30) return "I";
  if (num <= 45) return "N";
  if (num <= 60) return "G";
  return "O";
};

// Traditional BingoBall Component
export const BingoBall = ({ number, letter, size = "default", animate = false }) => {
  const ballLetter = letter || getLetterForNumber(number);
  
  const sizeClasses = {
    small: "bingo-ball bingo-ball-small",
    default: "bingo-ball",
    large: "bingo-ball bingo-ball-large",
    mega: "bingo-ball bingo-ball-mega"
  };

  const colorClass = `bingo-ball-${ballLetter}`;
  
  const Component = animate ? motion.div : "div";
  const animationProps = animate ? {
    initial: { scale: 0, rotate: -180 },
    animate: { scale: 1, rotate: 0 },
    transition: { type: "spring", stiffness: 260, damping: 20 }
  } : {};

  return (
    <Component
      className={`${sizeClasses[size]} ${colorClass}`}
      data-testid={`bingo-ball-${number}`}
      {...animationProps}
    >
      <span className="flex flex-col items-center leading-none">
        <span className="text-[0.4em] opacity-80">{ballLetter}</span>
        <span>{number}</span>
      </span>
    </Component>
  );
};

// Music Bingo Ball Component (NEW)
export const MusicBingoBall = ({ number, title, artist, size = "default", animate = false }) => {
  const sizeConfig = {
    small: { ball: "w-16 h-16", title: "text-xs", artist: "text-[10px]", number: "text-lg" },
    default: { ball: "w-24 h-24", title: "text-sm", artist: "text-xs", number: "text-2xl" },
    large: { ball: "w-40 h-40", title: "text-base", artist: "text-sm", number: "text-4xl" },
    mega: { ball: "w-64 h-64", title: "text-xl", artist: "text-base", number: "text-6xl" }
  };

  const config = sizeConfig[size];
  
  const Component = animate ? motion.div : "div";
  const animationProps = animate ? {
    initial: { scale: 0, rotate: -180 },
    animate: { scale: 1, rotate: 0 },
    transition: { type: "spring", stiffness: 260, damping: 20 }
  } : {};

  return (
    <Component
      className="flex flex-col items-center"
      data-testid={`music-ball-${number}`}
      {...animationProps}
    >
      {/* Vinyl Record Style Ball */}
      <div className={`${config.ball} rounded-full bg-gradient-to-br from-fuchsia-500 via-purple-600 to-fuchsia-700 flex items-center justify-center relative shadow-2xl`}
        style={{
          boxShadow: `
            inset -8px -8px 20px rgba(0,0,0,0.4),
            inset 8px 8px 20px rgba(255,255,255,0.2),
            0 10px 30px rgba(217, 70, 239, 0.5)
          `
        }}
      >
        {/* Inner circle (like vinyl label) */}
        <div className="absolute w-[40%] h-[40%] rounded-full bg-zinc-900 flex items-center justify-center">
          <span className={`font-display ${config.number} text-fuchsia-400`}>
            {number}
          </span>
        </div>
        {/* Shine effect */}
        <div className="absolute top-[10%] left-[20%] w-[30%] h-[20%] bg-gradient-to-br from-white/30 to-transparent rounded-full" />
      </div>
      
      {/* Song Info */}
      <div className="mt-3 text-center">
        <p className={`font-bold text-white ${config.title} truncate max-w-[200px]`}>{title}</p>
        <p className={`text-zinc-400 ${config.artist} truncate max-w-[200px]`}>{artist}</p>
      </div>
    </Component>
  );
};

// BingoBoard Component (Traditional)
export const BingoBoard = ({ calledNumbers = [], size = "default" }) => {
  const letters = ["B", "I", "N", "G", "O"];
  const ranges = [
    { start: 1, end: 15 },   // B
    { start: 16, end: 30 },  // I
    { start: 31, end: 45 },  // N
    { start: 46, end: 60 },  // G
    { start: 61, end: 75 }   // O
  ];

  const calledSet = useMemo(() => new Set(calledNumbers), [calledNumbers]);

  const cellSize = size === "small" ? "w-8 h-8 text-xs" : "w-12 h-12 text-sm";
  const headerSize = size === "small" ? "text-lg" : "text-xl";

  return (
    <div className="bingo-board" data-testid="bingo-board">
      {/* Header Row */}
      {letters.map((letter) => (
        <div
          key={`header-${letter}`}
          className={`bingo-board-cell header ${headerSize}`}
        >
          {letter}
        </div>
      ))}

      {/* Number Cells */}
      {Array.from({ length: 15 }, (_, row) => (
        letters.map((letter, col) => {
          const number = ranges[col].start + row;
          const isCalled = calledSet.has(number);
          
          return (
            <motion.div
              key={number}
              className={`bingo-board-cell ${cellSize} ${isCalled ? "called" : ""}`}
              initial={false}
              animate={isCalled ? { scale: [1, 1.1, 1] } : {}}
              transition={{ duration: 0.3 }}
              data-testid={`board-cell-${number}`}
            >
              {number}
            </motion.div>
          );
        })
      ))}
    </div>
  );
};

// Music Bingo Song Board Component (NEW)
export const MusicBingoBoard = ({ songs = [], calledSongs = [], size = "default" }) => {
  const calledSet = useMemo(() => new Set(calledSongs.map(s => s.number)), [calledSongs]);

  return (
    <div className="grid grid-cols-5 gap-2" data-testid="music-bingo-board">
      {songs.map((song) => {
        const isCalled = calledSet.has(song.number);
        
        return (
          <motion.div
            key={song.number}
            className={`p-3 rounded-lg text-center transition-all ${
              isCalled 
                ? "bg-fuchsia-500/30 border-2 border-fuchsia-500 scale-105" 
                : "bg-zinc-800/50 border border-zinc-700"
            }`}
            initial={false}
            animate={isCalled ? { scale: [1, 1.05, 1] } : {}}
            transition={{ duration: 0.3 }}
          >
            <span className={`font-mono text-lg ${isCalled ? "text-fuchsia-300" : "text-zinc-400"}`}>
              #{song.number}
            </span>
            <p className={`text-sm font-semibold truncate ${isCalled ? "text-white" : "text-zinc-300"}`}>
              {song.title}
            </p>
            <p className="text-xs text-zinc-500 truncate">{song.artist}</p>
          </motion.div>
        );
      })}
    </div>
  );
};

// Celebration Overlay
export const CelebrationOverlay = ({ winnerName, onClose }) => {
  return (
    <motion.div
      className="celebration-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <div className="text-center">
        <motion.h1
          className="celebration-text"
          initial={{ scale: 0, rotate: -20 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 10 }}
        >
          BINGO!
        </motion.h1>
        {winnerName && (
          <motion.p
            className="text-4xl text-white mt-8 font-display"
            initial={{ y: 50, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.3 }}
          >
            Winner: {winnerName}
          </motion.p>
        )}
      </div>
    </motion.div>
  );
};

// Ball Animation for Round Start
export const BallsRollingAnimation = ({ onComplete }) => {
  const balls = Array.from({ length: 20 }, (_, i) => ({
    id: i,
    number: Math.floor(Math.random() * 75) + 1,
    delay: Math.random() * 0.5,
    y: Math.random() * 100 - 50,
    duration: 1 + Math.random() * 0.5
  }));

  return (
    <motion.div
      className="fixed inset-0 z-50 pointer-events-none overflow-hidden"
      initial={{ opacity: 1 }}
      animate={{ opacity: 0 }}
      transition={{ delay: 2, duration: 0.5 }}
      onAnimationComplete={onComplete}
    >
      {balls.map((ball) => (
        <motion.div
          key={ball.id}
          className="absolute"
          style={{ top: `${30 + ball.y}%` }}
          initial={{ x: "-100px" }}
          animate={{ x: "calc(100vw + 100px)" }}
          transition={{
            duration: ball.duration,
            delay: ball.delay,
            ease: "linear"
          }}
        >
          <BingoBall number={ball.number} size="default" />
        </motion.div>
      ))}
    </motion.div>
  );
};

export default {
  BingoBall,
  MusicBingoBall,
  BingoBoard,
  MusicBingoBoard,
  CelebrationOverlay,
  BallsRollingAnimation
};
