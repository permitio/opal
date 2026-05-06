package audit.validation.user.verify.policy_0604

# Auto-generated policy 604 (Rego v1 syntax)
# Package: audit.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0604",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0604_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0604_allowed if {
    input.user.role == "admin"
}
policy_0604_allowed if {
    input.user.active
    input.resource.public
}
