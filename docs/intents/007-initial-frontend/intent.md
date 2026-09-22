---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-19
updated: 2026-09-22
stage: approved
milestone: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/milestones/13
---
# Initial Frontend

Initial Frontent. Goal is to provide the frontend base, utilizing the formerly
created backend functions. What we need in this Intent:

* any page requires authentication, unauthenticated users are redirected to the
  auth screen for sign-in/-up
* A Dashboard, showing own and participated started campaigns and a "new
  Campaign" CTA
* "New Campaign" triggers a "Select" dialog for choosing the campaign (currently
  only one available)
* When campaign is chosen, campaign run should be created
* Next screen is the campaign run screen, showing:
   * players list (one fore now) with state ( character ready ? )
      * when character isn't created, "create character Button" ("Create
        Character" will be next intent)
   * adventure list (one for now) with status
      * "start" CTA for next available campaign (disabled unless all characters
        are ready)

**Context (not part of the wish):** this intent does not follow the old phased
roadmap; `docs/roadmap/` is no longer a reference.
