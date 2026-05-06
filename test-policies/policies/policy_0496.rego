package governance.enforcement.policy.allow.policy_0496

# Auto-generated policy 496 (Rego v1 syntax)
# Package: governance.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0496",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0496_allowed if {
    input.user.role == "admin"
}
default policy_0496_allowed = false
