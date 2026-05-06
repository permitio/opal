package risk.authorization.action.deny.logic.policy_0535

# Auto-generated policy 535 (Rego v1 syntax)
# Package: risk.authorization.action.deny.logic

# Metadata
metadata := {
    "policy_id": "0535",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0535_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0535_allowed = false
policy_0535_allowed if {
    input.user.role == "admin"
}
policy_0535_allowed if {
    data.policies.risk.enabled
}
