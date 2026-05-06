package audit.validation.context.verify.helpers.policy_0593

# Auto-generated policy 593 (Rego v1 syntax)
# Package: audit.validation.context.verify.helpers

# Metadata
metadata := {
    "policy_id": "0593",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0593_allowed if {
    input.user.role == "admin"
}
default policy_0593_allowed = false
policy_0593_allowed if {
    input.user.active
    input.resource.public
}
policy_0593_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
