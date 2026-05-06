package risk.validation.user.verify.logic.policy_0900

# Auto-generated policy 900 (Rego v1 syntax)
# Package: risk.validation.user.verify.logic

# Metadata
metadata := {
    "policy_id": "0900",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0900_allowed if {
    data.policies.risk.enabled
}
default policy_0900_allowed = false
