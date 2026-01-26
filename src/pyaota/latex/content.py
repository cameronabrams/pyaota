"""
LaTeX content templates for pyaota.
"""

HEADMATTER = r"""
\documentclass[12pt, letter]{article}
\usepackage[margin=1in]{geometry}
\usepackage{fancyhdr}
\usepackage{setspace}
\usepackage{enumitem}
\usepackage{verbatim}
\usepackage{listings}
\usepackage{xcolor}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{upquote}
\usepackage[scaled]{helvet}
\renewcommand\familydefault{\sfdefault}
\usepackage{pifont}
\usepackage{tikz}
\usetikzlibrary{calc}
\usepackage{qrcode}
\usepackage{multicol}


\definecolor{bubblegray}{gray}{0.3}

\newcommand{\circledletter}[1]{%
  \tikz[baseline=-0.6ex]{%
    \node[
      circle,
      draw,
      inner sep=0pt,
      minimum size=1.1em,      % slightly larger bubble
      font=\footnotesize,   % <-- larger than scriptsize
      text height=1.5ex,       % fixed bounding box height
      text depth=0.4ex,        % fixed bounding box depth
      anchor=center
    ] {\textcolor{bubblegray}{#1}};
  }%
}

\newcommand{\idboxwbubbles}{%
  \tikz[baseline=-0.6ex]{
    \node[draw, minimum width=0.7cm, minimum height=0.7cm] (box) at (0,0) {};
    \foreach \i in {0,...,9} {
      \node at (0, -0.7 - \i*0.5) {\circledletter{\i}};
    }
  }%
}

\newcommand{\idboxes}[1][8]{%
  \foreach \i in {1,...,#1}{\idboxwbubbles\hspace{0.15cm}}%
}

\newcommand{\correctlabel}[1]{%
  \tikz[baseline=(char.base)]{
    \node[
      circle,
      fill=black,
      draw=black,
      inner sep=0pt,
      minimum size=1.0em,
      font=\normalsize
    ] (char) {\textcolor{white}{#1}};
  }%
}

\definecolor{lightlightgray}{gray}{0.9}\lstdefinestyle{mypython}{
  language=Python,
  basicstyle=\ttfamily\small,
  showstringspaces=false,
  breaklines=true,
  upquote=true,
  commentstyle=\ttfamily\upshape,
}
\newcommand{\inl}[1]{\lstinline[style=mypython]|#1|}
\lstdefinestyle{pseudocode}{
    basicstyle=\ttfamily,
    keywordstyle=\bfseries,
    keywords={if,then,else,elseif,while,for,return,end,endif,endwhile,endfor,print},
    columns=fullflexible,
    frame=single,
    mathescape=true,
    escapechar=§
}

\newcommand{\blank}[1][2cm]{\underline{\hspace{#1}}}
\newcommand{\smallblank}[1][0.5cm]{\ \underline{\hspace{#1}}\ }

\newif\ifshowanswers
\showanswersfalse

\newcounter{question}

\newenvironment{mcq}[3]{%
  \refstepcounter{question}%
  \par\medskip
  \def\questionid{#1}%
  \def\questionpoints{#2}%
  \def\questioncorrect{#3}%
  \noindent\begin{minipage}{\linewidth}%
    \textbf{\thequestion.}\enspace
}{%
  \end{minipage}%
  \par\bigskip
  \par\bigskip
}

\newenvironment{tf}[3]{%
  \refstepcounter{question}%
  \par\medskip
  \def\questionid{#1}%
  \def\questionpoints{#2}%
  \def\questioncorrect{#3}%
  \noindent\begin{minipage}{\linewidth}%
    \textbf{\thequestion.}\enspace
}{%
  \end{minipage}%
  \par\bigskip
  \par\bigskip
}

\newenvironment{choices}{%
  \begin{enumerate}[label=\alph*., leftmargin=2em]
}{%
  \end{enumerate}
}

\newcommand{\choice}[2][]{%
  \item[#1] #2%
}

\newcommand{\choicecode}[1][]{%
  \item[#1]
}
\setlength{\parindent}{0pt}
"""

DEFAULT_PAGESTYLES_TEMPLATE = r"""
\pagestyle{fancy}
\fancyhf{}
\rhead{<<<INSTITUTION>>> -- <<<COURSE>>> --- <<<TERM>>>}
\lhead{<<<DOCUMENTNAME>>> {\footnotesize (ver. <<<VERSION>>>)}}
\rfoot{\thepage}

% Special pagestyle for answer sheet: same header, no footer / page number
\fancypagestyle{answersheet}{%
  \fancyhf{}%
  \rhead{<<<INSTITUTION>>> -- <<<COURSE>>> --- <<<TERM>>>}%
  \lhead{<<<DOCUMENTNAME>>> {\footnotesize (ver. <<<VERSION>>>)}}%
  \rfoot{}
}
"""

BEGIN_DOCUMENT = r"""

\begin{document}

"""

DEFAULT_EXAM_INSTRUCTIONS = r"""
INSTRUCTIONS:
\begin{enumerate}
\item Be sure you have a pencil and an eraser.
\item \textbf{Carefully} detach the answer sheet from the back of this exam packet.
\item Enter your name and student ID number on the answer sheet in the spaces provided, and fill in the corresponding bubbles for each digit of your student ID.
\item Fill in the bubbles on the answer sheet corresponding to your answers.  You only get one answer sheet so do not lose it or damage it!
\item Time allowed: 60 minutes.
\item Any use of phones, calculators, notes, textbooks, or other aids is strictly prohibited.
\item \textbf{Turn in only your answer sheet}.  You should keep your exam packet for later review.
\end{enumerate}
Questions begin on the next page.
\clearpage
"""

QUESTION_BANK_DUMP_INSTRUCTIONS = r"""
This document contains a full dump of all questions in the selected question banks.
Questions begin on the next page.
\clearpage
"""


DEFAULT_ANSWER_SHEET_INSTRUCTIONS = r"""
Your name: \underline{\hspace{12cm}}\\*[0.5em]
\begin{minipage}[t]{0.4\linewidth}
\raggedleft
Your Drexel Student ID:\\
Please fill in a bubble for each digit of your ID:\\*[0.5em]
\begin{center}
\qrcode[height=1cm]{<<<VERSION>>>}\\*[0.5em]
{\footnotesize Version: <<<VERSION>>>}
\end{center}
\end{minipage}\ \ 
\begin{minipage}[t]{0.6\linewidth}
\idboxes[8]
\end{minipage}
Please fill in one bubble per question.  Give only this page to a TA or instructor at the end of the exam.
"""

ENDMESSAGE = r"""
\begin{center}
    \textbf{End of Exam}
\end{center}
"""

END_DOCUMENT = r"""
\end{document}
"""
