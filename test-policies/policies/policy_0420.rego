package risk.validation.context.verify.policy_0420

# Auto-generated policy 420 (Rego v1 syntax)
# Package: risk.validation.context.verify

# Metadata
metadata := {
    "policy_id": "0420",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0420_allowed if {
    data.policies.risk.enabled
}
policy_0420_allowed if {
    input.user.role == "admin"
}
default policy_0420_allowed = false
