package risk.enforcement.policy.deny.policy_0417

# Auto-generated policy 417 (Rego v1 syntax)
# Package: risk.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0417",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0417_allowed = false
policy_0417_allowed if {
    input.user.role == "admin"
}
