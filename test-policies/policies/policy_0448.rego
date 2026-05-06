package audit.authentication.context.deny.policy_0448

# Auto-generated policy 448 (Rego v1 syntax)
# Package: audit.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0448",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0448_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0448_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0448_allowed if {
    input.user.active
    input.resource.public
}
