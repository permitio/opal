package risk.authentication.action.check.helpers.policy_0376

# Auto-generated policy 376 (Rego v1 syntax)
# Package: risk.authentication.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0376",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0376_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0376_allowed if {
    input.user.role == "admin"
}
policy_0376_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0376_allowed if {
    input.user.active
    input.resource.public
}
