package audit.validation.action.validate.policy_0198

# Auto-generated policy 198 (Rego v1 syntax)
# Package: audit.validation.action.validate

# Metadata
metadata := {
    "policy_id": "0198",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0198_allowed = false
policy_0198_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0198_allowed if {
    input.user.active
    input.resource.public
}
policy_0198_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
