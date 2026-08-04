/*
  CODEAI SECURE BACKEND
  Node.js + Express + Anthropic

  Install:

  npm init -y
  npm install express cors dotenv

  Run:

  node server.js
*/

require("dotenv").config();

const express = require("express");
const cors = require("cors");

const app = express();

const PORT =
  process.env.PORT || 3000;

const ANTHROPIC_KEY =
  process.env.ANTHROPIC_API_KEY;

const MODEL =
  process.env.ANTHROPIC_MODEL ||
  "claude-sonnet-4-6";


/* =========================
   SECURITY / MIDDLEWARE
========================= */

app.use(
  cors({
    origin:"*"
  })
);

app.use(
  express.json({
    limit:"10mb"
  })
);


/* =========================
   HEALTH
========================= */

app.get(
  "/health",
  (req,res)=>{

    res.json({
      ok:true,
      service:"CodeAI Agent"
    });

  }
);


/* =========================
   ANTHROPIC CALL
========================= */

async function callClaude(
  system,
  user
){

  if(!ANTHROPIC_KEY){

    throw new Error(
      "ANTHROPIC_API_KEY server-এ সেট করা নেই।"
    );

  }

  const response =
   await fetch(
    "https://api.anthropic.com/v1/messages",
    {
     method:"POST",

     headers:{
      "Content-Type":
       "application/json",

      "x-api-key":
       ANTHROPIC_KEY,

      "anthropic-version":
       "2023-06-01"
     },

     body:JSON.stringify({

      model:MODEL,

      max_tokens:12000,

      system:system,

      messages:[
       {
        role:"user",
        content:user
       }
      ]

     })
    }
   );


  const data =
   await response.json();


  if(!response.ok){

    throw new Error(
      data?.error?.message ||
      "Anthropic API error"
    );

  }


  return (
    data?.content
      ?.filter(
       x=>x.type==="text"
      )
      ?.map(
       x=>x.text
      )
      ?.join("\n")
      ?.trim()
  ) || "";

}


/* =========================
   BUILD PROJECT CONTEXT
========================= */

function buildContext(files){

  if(!Array.isArray(files) ||
     !files.length){

    return "No project files were provided.";

  }

  return files
   .map(
    file => {

     const name =
      String(file.name || "unknown");

     const content =
      String(file.content || "");

     return `
==============================
FILE: ${name}
==============================

${content}

==============================
END FILE
==============================
`;

    }
   )
   .join("\n");

}


/* =========================
   AI AGENT
========================= */

app.post(
 "/api/agent",
 async(req,res)=>{

  try{

   const {
    mode,
    prompt,
    files
   } = req.body || {};


   if(!prompt){

    return res.status(400).json({
     error:"AI instruction missing"
    });

   }


   const project =
    buildContext(files);


   /* =========================
      FIRST AI PASS
   ========================= */

   const system = `

You are CODEAI, an expert autonomous
software engineering agent.

You are working on a real software project.

Your job is to understand the user's
request and produce the best complete
implementation possible.

IMPORTANT RULES:

1. Analyse ALL provided files.
2. Understand relationships between files.
3. Do not blindly modify code.
4. Find syntax bugs.
5. Find runtime bugs.
6. Find logical bugs.
7. Find security problems.
8. Find dependency problems.
9. Check API usage.
10. Check mobile/browser compatibility.
11. Preserve existing functionality unless
    the user explicitly asks to change it.
12. Never return a tiny snippet when a
    complete file is required.

If files need modification, output the
COMPLETE changed files.

Use this format:

FILE: filename.ext

\`\`\`language
COMPLETE FILE CONTENT
\`\`\`

Repeat for every changed/new file.

At the end include:

PROJECT_STATUS:
READY

No incomplete code.
No pseudo-code.
No "rest of code here".
No omitted sections.

`;


   const user =
`
MODE:
${mode}

USER REQUEST:
${prompt}

PROJECT FILES:

${project}
`;


   const first =
    await callClaude(
     system,
     user
    );


   if(!first){

    throw new Error(
     "First AI returned empty response"
    );

   }


   /* =========================
      SECOND INDEPENDENT REVIEW
   ========================= */

   const reviewSystem = `

You are CODEAI QA ENGINE.

You are performing an independent
second-pass code review.

Do NOT trust the first AI.

Review the complete proposed solution
line by line.

Check:

- Syntax
- Runtime errors
- Logic
- Security
- Authentication
- Authorization
- Input validation
- API handling
- Async problems
- Null/undefined problems
- File paths
- Imports
- Dependencies
- Browser compatibility
- Mobile compatibility
- Performance
- Edge cases
- Broken assumptions
- Incomplete code
- Missing functions
- Incorrect variable names

If you find ANY problem:

FIX IT.

Return the complete corrected files.

Use:

FILE: filename.ext

\`\`\`language
COMPLETE CORRECTED FILE
\`\`\`

Never return a diff.

Never return partial code.

Never say "unchanged" instead of
showing the complete file.

At the end:

QA_STATUS:
READY

`;


   const reviewUser =
`
ORIGINAL USER REQUEST:

${prompt}

ORIGINAL PROJECT:

${project}

FIRST AI IMPLEMENTATION:

${first}

Perform an independent QA review and
return the final corrected implementation.
`;


   const final =
    await callClaude(
     reviewSystem,
     reviewUser
    );


   if(!final){

    throw new Error(
     "QA review returned empty response"
    );

   }


   res.json({

    ok:true,

    output:final

   });


  }catch(error){

   console.error(
    "CODEAI ERROR:",
    error
   );

   res.status(500).json({

    error:
     error?.message ||
     "Internal server error"

   });

  }

 });


/* =========================
   START
========================= */

app.listen(
 PORT,
 ()=>{

  console.log(
   `CodeAI server running on port ${PORT}`
  );

 }
);
