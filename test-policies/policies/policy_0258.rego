package access.validation.context.deny.policy_0258

# Auto-generated policy 258 (Rego v1 syntax)
# Package: access.validation.context.deny

# Metadata
metadata := {
    "policy_id": "0258",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0258_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0258_allowed if {
    input.user.role == "admin"
}
default policy_0258_allowed = false
