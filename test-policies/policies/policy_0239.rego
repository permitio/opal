package risk.authentication.policy.validate.policy_0239

# Auto-generated policy 239 (Rego v1 syntax)
# Package: risk.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0239",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0239_allowed if {
    input.user.role == "admin"
}
default policy_0239_allowed = false
