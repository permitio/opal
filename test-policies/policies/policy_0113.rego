package audit.enforcement.policy.check.helpers.policy_0113

# Auto-generated policy 113 (Rego v1 syntax)
# Package: audit.enforcement.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0113",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0113_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0113_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0113_allowed if {
    input.user.role == "admin"
}
policy_0113_allowed if {
    input.user.active
    input.resource.public
}
