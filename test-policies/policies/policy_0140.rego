package access.enforcement.user.verify.data.policy_0140

# Auto-generated policy 140 (Rego v1 syntax)
# Package: access.enforcement.user.verify.data

# Metadata
metadata := {
    "policy_id": "0140",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0140_allowed if {
    input.user.role == "admin"
}
default policy_0140_allowed = false
