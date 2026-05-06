package compliance.authorization.user.verify.policy_0842

# Auto-generated policy 842 (Rego v1 syntax)
# Package: compliance.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0842",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0842_allowed = false
policy_0842_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
