require("dotenv").config();

const express = require("express");
const cors = require("cors");
const OpenAI = require("openai");

const app = express();

const PORT = process.env.PORT || 3000;
const MODEL = process.env.OPENAI_MODEL || "gpt-5";

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});


/* =========================
   MIDDLEWARE
========================= */

app.use(
  cors({
    origin: "*",
    methods: ["GET", "POST", "OPTIONS"],
    allowedHeaders: ["Content-Type"]
  })
);

app.use(
  express.json({
    limit: "15mb"
  })
);


/* =========================
   HOME
========================= */

app.get("/", (req, res) => {

  res.json({
    ok: true,
    service: "CODEAI Backend",
    provider: "OpenAI",
    model: MODEL,
    status: "online"
  });

});


/* =========================
   HEALTH
========================= */

app.get("/health", (req, res) => {

  res.json({
    ok: true,
    service: "CODEAI Agent",
    provider: "OpenAI",
    model: MODEL,
    status: "online"
  });

});


/* =========================
   OPENAI FUNCTION
========================= */

async function callOpenAI(instructions, input) {

  if (!process.env.OPENAI_API_KEY) {

    throw new Error(
      "OPENAI_API_KEY Render Environment Variables-এ সেট করা নেই।"
    );

  }

  const response =
    await openai.responses.create({

      model: MODEL,

      instructions: instructions,

      input: input,

      max_output_tokens: 12000

    });


  const text =
    response.output_text || "";


  if (!text.trim()) {

    throw new Error(
      "OpenAI থেকে কোনো response পাওয়া যায়নি।"
    );

  }


  return text.trim();

}


/* =========================
   PROJECT CONTEXT
========================= */

function buildProjectContext(files) {

  if (
    !Array.isArray(files) ||
    files.length === 0
  ) {

    return "No project files were provided.";

  }


  return files
    .map((file) => {

      const name =
        String(
          file?.name || "unknown"
        );

      const content =
        String(
          file?.content || ""
        );


      return `
==============================
FILE: ${name}
==============================

${content}

==============================
END FILE
==============================
`;

    })
    .join("\n");

}


/* =========================
   CODEAI AGENT
========================= */

app.post(
  "/api/agent",
  async (req, res) => {

    try {

      const {
        mode,
        prompt,
        files
      } = req.body || {};


      /* =========================
         VALIDATION
      ========================= */

      if (
        !prompt ||
        !String(prompt).trim()
      ) {

        return res.status(400).json({

          ok: false,

          error:
            "AI instruction missing."

        });

      }


      const project =
        buildProjectContext(files);


      /* =========================
         FIRST AI PASS
      ========================= */

      const firstInstructions = `

You are CODEAI.

You are an expert autonomous
software engineering assistant.

You help users:

- Generate code
- Fix bugs
- Debug projects
- Analyse errors
- Improve existing code
- Review architecture
- Find security problems
- Fix API problems
- Fix frontend problems
- Fix backend problems
- Fix mobile/browser problems

IMPORTANT RULES:

1. Analyse ALL provided files.

2. Understand how files
   work together.

3. Find syntax errors.

4. Find runtime errors.

5. Find logical errors.

6. Find security vulnerabilities.

7. Find dependency problems.

8. Find API problems.

9. Check imports.

10. Check exports.

11. Check async/await.

12. Check null and undefined issues.

13. Check browser compatibility.

14. Check mobile compatibility.

15. Preserve existing functionality.

16. Do not use pseudo-code.

17. Do not use placeholders.

18. Never write:
"rest of code here".

19. Never provide incomplete code.

20. If a file must be changed,
return the COMPLETE file.

OUTPUT FORMAT:

FILE: filename.ext

\`\`\`language
COMPLETE FILE CONTENT
\`\`\`

Repeat this for every changed
or newly created file.

At the end write:

PROJECT_STATUS:
READY

MODE:
${mode || "unknown"}

`;


      const firstInput = `

USER REQUEST:

${prompt}

==============================

PROJECT FILES:

${project}

==============================

Create the best complete
implementation possible.

`;


      const first =
        await callOpenAI(
          firstInstructions,
          firstInput
        );


      /* =========================
         SECOND QA PASS
      ========================= */

      const qaInstructions = `

You are CODEAI QA ENGINE.

You are an independent senior
software engineer performing a
second-pass code review.

DO NOT blindly trust the
first AI implementation.

Review the implementation
carefully.

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
- Promise handling
- Null values
- Undefined values
- Imports
- Exports
- Dependencies
- File paths
- Browser compatibility
- Android compatibility
- Performance
- Edge cases
- Incorrect assumptions
- Missing functions
- Wrong variable names
- Incomplete code

If you find ANY problem:

FIX IT.

Return the COMPLETE corrected
files.

Never return a diff.

Never return partial code.

Never say:
"unchanged".

Always provide the complete
file when a file is included.

OUTPUT FORMAT:

FILE: filename.ext

\`\`\`language
COMPLETE CORRECTED FILE
\`\`\`

Repeat for every changed file.

At the end write:

QA_STATUS:
READY

`;


      const qaInput = `

ORIGINAL USER REQUEST:

${prompt}

==============================

ORIGINAL PROJECT:

${project}

==============================

FIRST AI IMPLEMENTATION:

${first}

==============================

Perform an independent QA
review.

Fix every problem you find.

Return the final complete
implementation.

`;


      const final =
        await callOpenAI(
          qaInstructions,
          qaInput
        );


      /* =========================
         RESPONSE
      ========================= */

      res.json({

        ok: true,

        provider: "OpenAI",

        model: MODEL,

        output: final

      });


    } catch (error) {

      console.error(
        "CODEAI ERROR:",
        error
      );


      res.status(500).json({

        ok: false,

        error:
          error?.message ||
          "Internal server error."

      });

    }

  }
);


/* =========================
   404
========================= */

app.use(
  (req, res) => {

    res.status(404).json({

      ok: false,

      error:
        "Endpoint not found."

    });

  }
);


/* =========================
   START SERVER
========================= */

app.listen(
  PORT,
  () => {

    console.log(
      `CODEAI Backend running on port ${PORT}`
    );

    console.log(
      `Provider: OpenAI`
    );

    console.log(
      `Model: ${MODEL}`
    );

  }
);
