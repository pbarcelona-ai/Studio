# Kaggle limits a notebook's title (and so its slug, which must equal the title with dashes for spaces) to 50 characters, and a dataset's too.
# A long book name made "<book>-<model>-keyframes-1-40" longer than that, and Kaggle answered "400 Bad Request" when the notebook was pushed.
#   kaggle_fit <name> <tail>   prints <name><tail> in at most 50 characters: a name that is too long is cut and given a short number from its
#                              full text, so two long names that start alike stay different (the same name always gives the same result)
kaggle_fit() {
  local name="$1" tail="$2" max h cut
  max=$((50 - ${#tail}))
  if [ "${#name}" -le "$max" ]; then printf '%s%s' "$name" "$tail"; return; fi
  h=$(printf '%s' "$name" | cksum | cut -d' ' -f1 | cut -c1-5)
  cut=$(printf '%s' "${name:0:$((max - 6))}" | sed 's/-*$//')
  printf '%s-%s%s' "$cut" "$h" "$tail"
}
