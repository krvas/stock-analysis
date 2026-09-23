1. The git commit history is messy. There was some AI generated code
   that was badly written. On AI's suggestion, you tried to patch it,
   so your git looks like a bunch of patchwork. You will have to read
   and approve it, and then squash the appropriate commits. Figure out
   how to diff-view the same file after 4-5 commits of changes.
   - Fixed

2. The patchwork may not necessarily be complete. adjustment_post.py
   does not use your intended Table object to parse the incoming post
   request.

3. Your table object on the frontend now subscribes to changes in all
   its inputs. That's probably not scalable. You might have to do
   something different. You might consider react, or only subscribing
   to input elements, or make the changes on submit / on input change.

4. Implement better coding standards. You have a chat with Claude open
   for this. Also, your Claude code wrote a CLAUDE.md file which you
   need to evaluate.

5. There is an unconsidered edge case - what happens if you capitalize
   an opex, click submit, then change your mind?